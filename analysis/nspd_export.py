"""Deduplicate collected NSPD objects, export WKT Parquet in EPSG:4326 and QA.

No network requests. Raw files were already sanitized by nspd_collect.py.
The guide's rectangle is not an administrative Moscow boundary.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np
import pandas as pd
from shapely.geometry import shape
from shapely.ops import transform

from nspd_collect import GROUPS, RIGHTS, split4, strip_rights

LAYERS = {36369:'buildings', 36384:'construction', 36383:'structures',
    36368:'parcels', 38981:'auction_parcels', 38979:'available_parcels',
    37158:'planned_parcels', 36940:'restricted_zones', 472825:'protected_areas',
    472820:'heritage', 472853:'forest_parks', 472813:'water_472813',
    472816:'water_472816', 36381:'cadastral_quarters', 472819:'territorial_zones'}
BBOX = (55.49, 55.96, 37.30, 37.90)


def to_4326(x, y, z=None):
    x, y = np.asarray(x), np.asarray(y)
    return x/6378137*180/math.pi, np.arctan(np.sinh(y/6378137))*180/math.pi


def max_floor(value):
    numbers = re.findall(r'\d+', str(value)) if value is not None else []
    return max(map(int, numbers)) if numbers else None


def numeric(value):
    if value is None or pd.isna(value) or value == '':
        return None
    try:
        n = float(str(value).replace('\xa0', '').replace(' ', '').replace(',', '.'))
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def object_key(f):
    p = f.get('properties') or {}
    identifier = f.get('id')
    if identifier is None:
        identifier = p.get('externalKey') or (p.get('options') or {}).get('cad_num')
    if identifier is None:
        # Never collapse all unidentified features into a single (category, None).
        identifier = 'sha256:'+hashlib.sha256(json.dumps(strip_rights(f), sort_keys=True,
            ensure_ascii=False).encode()).hexdigest()
    return int(p['category']), str(identifier)


def completeness(directory, groups):
    summary = {}
    tiles = []
    for group in groups:
        grid = pd.read_csv(directory/('tiles_4km.csv' if group == 'sparse' else 'tiles_2km.csv'))
        def ids(name):
            p = directory/f'{name}_{group}.txt'
            return set(p.read_text().split()) if p.exists() else set()
        done, split = ids('done'), ids('split')
        raw_tiles = set()
        raw_path = directory/f'raw_{group}.jsonl'
        if raw_path.exists():
            with raw_path.open() as fh:
                for line in fh:
                    if line.strip():
                        raw_tiles.add(json.loads(line)['tile'])
        missing_children = []
        missing_data = []
        for parent in sorted(split):
            missing_children += [f'{parent}/{i}' for i in range(1, 5) if f'{parent}/{i}' not in done]
        for tile in done-split:
            if tile not in raw_tiles:
                missing_data.append(tile)
        for t in grid.itertuples(index=False):
            tiles.append(dict(group=group, tile_id=t.tile_id, lon=(t.lon_min+t.lon_max)/2,
                lat=(t.lat_min+t.lat_max)/2, done=t.tile_id in done, split=t.tile_id in split))
        completed = sum(t in done for t in grid.tile_id)
        summary[group] = dict(total_root_tiles=len(grid), completed_root_tiles=completed,
            remaining_root_tiles=len(grid)-completed, leaf_responses=len(raw_tiles),
            split_tiles=len(split), missing_split_children=missing_children,
            completed_without_raw=missing_data,
            complete=completed == len(grid) and not missing_children and not missing_data)
    return summary, pd.DataFrame(tiles)


def export(directory, groups=('view',)):
    directory = Path(directory)
    dest = directory/'tables'
    dest.mkdir(parents=True, exist_ok=True)
    objects = {}
    counters = collections.Counter()
    for group in groups:
        path = directory/f'raw_{group}.jsonl'
        if not path.exists():
            continue
        with path.open(encoding='utf-8') as fh:
            for line in fh:
                if not line.strip():
                    continue
                record = json.loads(line)
                for feature in record['f']:
                    counters['raw_features'] += 1
                    f = strip_rights(feature)
                    if not f.get('geometry'):
                        counters['without_geometry'] += 1
                        continue
                    key = object_key(f)
                    updated = str(((f.get('properties') or {}).get('systemInfo') or {}).get('updated') or '')
                    if key in objects:
                        counters['duplicates'] += 1
                        if objects[key][0] >= updated:
                            continue
                    objects[key] = (updated, f, record['tile'], record['ts'])
    rows = []
    bad_geometry = []
    for (category, identifier), (updated, f, tile, collected_at) in objects.items():
        p = f.get('properties') or {}
        geom = f['geometry']
        source_crs = ((geom.get('crs') or {}).get('properties') or {}).get('name')
        if source_crs not in (None, 'EPSG:3857'):
            raise ValueError(f'Unexpected source CRS: {source_crs}')
        try:
            g = transform(to_4326, shape(geom))
            if g.is_empty:
                raise ValueError('empty geometry')
            c = g.representative_point()
            if not (35 < c.x < 40 and 54 < c.y < 58):
                raise ValueError('transformed coordinates outside Moscow region')
        except Exception as exc:
            bad_geometry.append(dict(cat=category, obj_id=identifier, error=str(exc)))
            continue
        opts = p.get('options') or {}
        row = {k:json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v) if v is not None else None
               for k, v in opts.items() if k not in RIGHTS}
        row.update(cat=category, obj_id=identifier, cad=p.get('externalKey'), upd=updated,
            source_tile=tile, collected_at=collected_at, lat=c.y, lon=c.x, wkt=g.wkt,
            geometry_valid=g.is_valid,
            within_requested_bbox=BBOX[0] <= c.y <= BBOX[1] and BBOX[2] <= c.x <= BBOX[3])
        rows.append(row)
    df = pd.DataFrame(rows)
    quality = dict(created_at=dt.datetime.now(dt.timezone.utc).isoformat(), crs='EPSG:4326',
        geometry_encoding='WKT', source_crs='EPSG:3857', requested_bbox_latlon=BBOX,
        boundary_note='Guide rectangle plus grid overlap, not the Moscow administrative boundary.',
        counts=dict(counters), invalid_geometry_records=len(bad_geometry), layers={})
    for category, name in LAYERS.items():
        if df.empty or category not in set(df.cat):
            continue
        part = df[df.cat == category].dropna(axis=1, how='all').copy()
        if category == 36369:
            part['floors_n'] = pd.array(part.get('floors', pd.Series(None, index=part.index)).map(max_floor), dtype='Int64')
        if category == 36368:
            part['area_m2'] = part.apply(lambda r: next((numeric(r.get(c)) for c in
                ['land_record_area', 'specified_area', 'declared_area'] if numeric(r.get(c)) is not None), None), axis=1)
        for col in part:
            if part[col].dtype == object:
                part[col] = part[col].astype('string')
        path = dest/f'moscow_{name}.parquet'
        temp = path.with_suffix('.parquet.tmp')
        part.to_parquet(temp, index=False)
        temp.replace(path)
        info = dict(category=category, objects=len(part), path=str(path.relative_to(directory)),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            invalid_topology=int((~part.geometry_valid).sum()),
            outside_requested_bbox=int((~part.within_requested_bbox).sum()))
        if category == 36369:
            positive = (part.floors_n.fillna(0) > 0)
            info.update(floors_present_fraction=float(part.floors_n.notna().mean()),
                floors_positive_fraction=float(positive.mean()),
                floors_missing=int(part.floors_n.isna().sum()), floors_zero=int((part.floors_n == 0).sum()))
        # Keep zero values distinct from missing values.
        info['numeric_fields'] = {}
        for col in ['build_record_area', 'cost_value', 'cost_index', 'height', 'volume', 'area_m2']:
            if col in part:
                vals=part[col].map(numeric)
                info['numeric_fields'][col] = dict(missing=int(vals.isna().sum()), zero=int((vals == 0).sum()))
        quality['layers'][name] = info
    summary, tiles = completeness(directory, groups)
    quality['coverage'] = summary
    quality['complete'] = all(v['complete'] for v in summary.values()) and not bad_geometry
    buildings = quality['layers'].get('buildings', {})
    quality['building_pilot_pass'] = bool(buildings and buildings.get('floors_positive_fraction', 0) >= .95
        and not bad_geometry and not any(v['completed_without_raw'] or v['missing_split_children'] for v in summary.values()))
    tiles.to_csv(dest/'tile_coverage.csv', index=False)
    if not df.empty:
        import plotly.graph_objects as go
        buildings=df[df.cat == 36369]
        fig=go.Figure(go.Scattergl(x=buildings.lon, y=buildings.lat, mode='markers',
            marker=dict(size=2, color='#245b9d', opacity=.6), name='Здания',
            hoverinfo='x+y'))
        for group in groups:
            grid=pd.read_csv(directory/('tiles_4km.csv' if group=='sparse' else 'tiles_2km.csv'))
            flags=tiles[tiles.group == group].set_index('tile_id').done
            for t in grid.itertuples(index=False):
                fig.add_shape(type='rect', x0=t.lon_min, x1=t.lon_max, y0=t.lat_min, y1=t.lat_max,
                    line=dict(color='#27935b' if flags[t.tile_id] else '#b6b6b6', width=.5), fillcolor='rgba(0,0,0,0)')
        fig.update_layout(title='НСПД: здания и сетка (зелёный — получено, серый — не получено)',
            xaxis_title='Долгота, EPSG:4326', yaxis_title='Широта, EPSG:4326', template='plotly_white',
            yaxis=dict(scaleanchor='x', scaleratio=1/math.cos(math.radians(55.751))))
        fig.write_html(dest/'coverage.html', include_plotlyjs=True, full_html=True)
    pd.DataFrame(bad_geometry, columns=['cat','obj_id','error']).to_csv(dest/'geometry_errors.csv', index=False)
    # cnt_oks_geom describes all capital-construction categories, not buildings alone.
    if not df.empty and (df.cat == 36381).any() and 'quarter_cad_number' in df:
        observed=df[df.cat.isin([36369, 36383, 36384])].groupby('quarter_cad_number').size()
        quarters=df[df.cat == 36381].copy()
        quarters['observed_oks_geom'] = quarters.cad.map(observed).fillna(0).astype(int)
        cols=[c for c in ['cad', 'cnt_oks', 'cnt_oks_geom', 'observed_oks_geom'] if c in quarters]
        quarters[cols].to_csv(dest/'quarter_completeness.csv', index=False)
        quality['quarter_note']='Partial boundary quarters and uncollected tiles affect counts; differences alone do not prove missing API objects.'
    tmp = dest/'quality.json.tmp'
    tmp.write_text(json.dumps(quality, ensure_ascii=False, indent=2)+'\n')
    tmp.replace(dest/'quality.json')
    print(json.dumps(dict(complete=quality['complete'], pilot_pass=quality['building_pilot_pass'],
        layers={k:v['objects'] for k,v in quality['layers'].items()}, coverage=summary), ensure_ascii=False), flush=True)
    return quality


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out', default='data/nspd_moscow')
    parser.add_argument('--groups', nargs='+', choices=list(GROUPS), default=['view'])
    args=parser.parse_args()
    export(args.out, args.groups)
