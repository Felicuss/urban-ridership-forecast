"""Reproduce the supplied guide's Moscow grids without network requests."""
import argparse
import math
from pathlib import Path
import pandas as pd


def make_tiles(tile_m):
    lat0, lon0 = 55.751, 37.618
    bbox = (55.49, 55.96, 37.30, 37.90)
    dlat = tile_m/111320
    dlon = tile_m/(111320*math.cos(math.radians(lat0)))
    rows = []
    for i in range(math.floor((bbox[0]-lat0)/dlat), math.floor((bbox[1]-lat0)/dlat)+1):
        for j in range(math.floor((bbox[2]-lon0)/dlon), math.floor((bbox[3]-lon0)/dlon)+1):
            lat, lon = lat0+i*dlat, lon0+j*dlon
            rows.append(dict(tile_id=f'msk{tile_m//1000}_{i}_{j}', lat_min=lat, lat_max=lat+dlat,
                             lon_min=lon, lon_max=lon+dlon))
    return pd.DataFrame(rows)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out', default='data/nspd_moscow')
    args=parser.parse_args()
    out=Path(args.out);out.mkdir(parents=True, exist_ok=True)
    for size, expected in [(2000, 513), (4000, 140)]:
        frame=make_tiles(size)
        assert len(frame) == expected
        path=out/f'tiles_{size//1000}km.csv'
        if path.exists():
            pd.testing.assert_frame_equal(frame, pd.read_csv(path))
        else:
            frame.to_csv(path, index=False)
        print(path, len(frame))
