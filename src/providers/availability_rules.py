import re
from typing import Any

from chalkbox.logging.bridge import get_logger

from src.providers.field_mapper import FieldMapper

logger = get_logger(__name__)


class AvailabilityRuleEngine:
    """Evaluates availability rules against JSON-LD data."""

    @staticmethod
    def evaluate(data: dict[str, Any], rules_config: dict[str, Any]) -> bool:
        """Evaluate availability rules against data."""
        if not rules_config or "rules" not in rules_config:
            return False

        rules = rules_config["rules"]
        logic = rules_config.get("logic", "OR").upper()

        if not rules:
            return False

        results: list[bool] = []
        for rule in rules:
            try:
                result = AvailabilityRuleEngine._evaluate_single_rule(data, rule)
                results.append(result)
                logger.debug(f"Rule {rule} → {result}")
            except Exception as e:
                logger.warning(f"Failed to evaluate rule {rule}: {e}")
                results.append(False)

        if logic == "AND":
            return all(results)
        else:  # OR
            return any(results)

    @staticmethod
    def _evaluate_single_rule(data: dict[str, Any], rule: dict[str, Any]) -> bool:
        """Evaluate a single rule."""
        rule_type = rule.get("type")

        if rule_type == "field_exists":
            return AvailabilityRuleEngine._evaluate_field_exists(data, rule)
        elif rule_type == "field_comparison":
            return AvailabilityRuleEngine._evaluate_field_comparison(data, rule)
        elif rule_type == "field_pattern":
            return AvailabilityRuleEngine._evaluate_field_pattern(data, rule)
        else:
            logger.warning(f"Unknown rule type: {rule_type}")
            return False

    @staticmethod
    def _evaluate_field_exists(data: dict[str, Any], rule: dict[str, Any]) -> bool:
        """Check if field exists and has non-empty value."""
        field_path = rule.get("field")
        if not field_path:
            return False

        value = FieldMapper.get_value(data, field_path)

        if value is None:
            return False

        if isinstance(value, str) and not value.strip():
            return False

        return (value, (list, dict)) and not value

    @staticmethod
    def _evaluate_field_comparison(data: dict[str, Any], rule: dict[str, Any]) -> bool:
        """Compare field value with expected value."""
        field_path = rule.get("field")
        operator = rule.get("operator")
        expected_value = rule.get("value")

        if not field_path or not operator:
            return False

        actual_value = FieldMapper.get_value(data, field_path)

        if actual_value is None:
            return False

        try:
            if isinstance(expected_value, (int, float)):
                actual_value = float(actual_value)

            if operator in (">", "<", ">=", "<="):
                if not isinstance(actual_value, (int, float, str)):
                    logger.warning(
                        f"Cannot compare value of type {type(actual_value).__name__} with operator {operator}"
                    )
                    return False
                if not isinstance(expected_value, (int, float, str)):
                    logger.warning(
                        f"Cannot compare with expected value of type {type(expected_value).__name__}"
                    )
                    return False

            if operator == ">":
                return bool(actual_value > expected_value)  # type: ignore[operator]
            elif operator == "<":
                return bool(actual_value < expected_value)  # type: ignore[operator]
            elif operator == "==":
                return bool(actual_value == expected_value)
            elif operator == "!=":
                return bool(actual_value != expected_value)
            elif operator == ">=":
                return bool(actual_value >= expected_value)  # type: ignore[operator]
            elif operator == "<=":
                return bool(actual_value <= expected_value)  # type: ignore[operator]
            else:
                logger.warning(f"Unknown operator: {operator}")
                return False

        except (ValueError, TypeError) as e:
            logger.warning(f"Comparison failed for {actual_value} {operator} {expected_value}: {e}")
            return False

    @staticmethod
    def _evaluate_field_pattern(data: dict[str, Any], rule: dict[str, Any]) -> bool:
        """Match field value against regex pattern."""
        field_path = rule.get("field")
        pattern = rule.get("pattern")

        if not field_path or not pattern:
            return False

        value = FieldMapper.get_value(data, field_path)

        if value is None:
            return False

        try:
            value_str = str(value)
            return bool(re.search(pattern, value_str))
        except Exception as e:
            logger.warning(f"Pattern match failed for {value} against {pattern}: {e}")
            return False
