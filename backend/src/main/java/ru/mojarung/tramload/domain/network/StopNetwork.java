package ru.mojarung.tramload.domain.network;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collectors;

import ru.mojarung.tramload.domain.ValidationException;

/**
 * Остановки и доли посадок. Прогноз остановки или участка - это прогноз маршрутов, умноженный на их доли,
 * поэтому сумма по всем остановкам маршрута равна прогнозу маршрута.
 */
public final class StopNetwork {

	private final Map<String, Stop> stops;
	private final List<RouteStop> routeStops;

	public StopNetwork(List<Stop> stops, List<RouteStop> routeStops) {
		this.stops = stops.stream().collect(Collectors.toUnmodifiableMap(Stop::id, Function.identity()));
		this.routeStops = routeStops.stream()
			.sorted(Comparator.comparingInt(RouteStop::route).thenComparingInt(RouteStop::direction)
				.thenComparingInt(RouteStop::seq))
			.toList();
		routeStops.stream().filter(rs -> !this.stops.containsKey(rs.stopId())).findFirst().ifPresent(rs -> {
			throw new IllegalArgumentException("остановки " + rs.stopId() + " маршрута " + rs.route() + " нет в stops.csv");
		});
	}

	public Optional<Stop> stop(String id) {
		return Optional.ofNullable(stops.get(id));
	}

	public List<Stop> stops() {
		return stops.values().stream().sorted(Comparator.comparing(Stop::id)).toList();
	}

	public List<RouteStop> routeStops(int route) {
		return routeStops.stream().filter(rs -> rs.route() == route).toList();
	}

	/** Веса маршрутов для остановки: сумма долей остановки на каждом маршруте в обоих направлениях. */
	public Map<Integer, Double> stopWeights(String stopId) {
		if (!stops.containsKey(stopId)) {
			throw ValidationException.of("id", "остановки " + stopId + " нет в сети");
		}
		Map<Integer, Double> weights = new TreeMap<>();
		routeStops.stream()
			.filter(rs -> rs.stopId().equals(stopId))
			.forEach(rs -> weights.merge(rs.route(), rs.share(), Double::sum));
		return weights;
	}

	/** Вес участка маршрута: доли остановок направления от fromStop до toStop включительно. */
	public Map<Integer, Double> segmentWeights(int route, int direction, String fromStop, String toStop) {
		List<RouteStop> line = routeStops.stream()
			.filter(rs -> rs.route() == route && rs.direction() == direction)
			.toList();
		if (line.isEmpty()) {
			throw ValidationException.of("direction", "у маршрута " + route + " нет направления " + direction);
		}
		int from = position(line, fromStop, "fromStop");
		int to = position(line, toStop, "toStop");
		if (from > to) {
			throw ValidationException.of("toStop", "остановка " + toStop + " идёт раньше " + fromStop + " по ходу рейса");
		}
		double share = line.subList(from, to + 1).stream().mapToDouble(RouteStop::share).sum();
		return Map.of(route, share);
	}

	/** Доли всех остановок по маршрутам: для карты считаем все остановки за один проход. */
	public Map<String, Map<Integer, Double>> allStopWeights() {
		Map<String, Map<Integer, Double>> out = new LinkedHashMap<>();
		routeStops.forEach(rs -> out.computeIfAbsent(rs.stopId(), k -> new TreeMap<>())
			.merge(rs.route(), rs.share(), Double::sum));
		return out;
	}

	private static int position(List<RouteStop> line, String stopId, String field) {
		for (int i = 0; i < line.size(); i++) {
			if (line.get(i).stopId().equals(stopId)) {
				return i;
			}
		}
		throw ValidationException.of(field, "остановки " + stopId + " нет на маршруте " + line.getFirst().route()
				+ " в направлении " + line.getFirst().direction());
	}

}
