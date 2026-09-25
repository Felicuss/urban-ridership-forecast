package ru.mojarung.tramload.infrastructure;

import java.util.ArrayList;
import java.util.List;

import tools.jackson.databind.JsonNode;

import ru.mojarung.tramload.domain.coefficient.CoefficientSpec;
import ru.mojarung.tramload.domain.coefficient.CoefficientType;

/** Разбор ползунков из coefficients.json: значения по умолчанию и границы приводятся к типу ползунка. */
final class CatalogParser {

	private CatalogParser() {
	}

	static List<CoefficientSpec> specs(JsonNode root) {
		List<CoefficientSpec> specs = new ArrayList<>();
		for (JsonNode item : root.path("coefficients")) {
			CoefficientType type = CoefficientType.parse(item.path("type").asString());
			String key = item.path("key").asString();
			try {
				specs.add(new CoefficientSpec(key, item.path("label").asString(), item.path("group").asString(), type,
						type.coerce(value(item.path("default"))), bound(type, item.path("min")),
						bound(type, item.path("max")), item.hasNonNull("step") ? item.get("step").asDouble() : null,
						item.path("source").asString()));
			}
			catch (IllegalArgumentException ex) {
				throw new ArtifactValidationException("coefficients.json, " + key + ": " + ex.getMessage(), ex);
			}
		}
		return specs;
	}

	private static Object bound(CoefficientType type, JsonNode node) {
		if (node.isMissingNode() || node.isNull()) {
			return null;
		}
		Object value = type.coerce(value(node));
		return value instanceof Integer i ? i.doubleValue() : value;
	}

	private static Object value(JsonNode node) {
		if (node.isNumber()) {
			return node.numberValue();
		}
		if (node.isBoolean()) {
			return node.booleanValue();
		}
		return node.isString() ? node.stringValue() : null;
	}

}
