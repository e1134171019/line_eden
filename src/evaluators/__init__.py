# -*- coding: utf-8 -*-

from src.evaluators.production_rule_scope_guard import (
    install_production_rule_scope_guard,
)
from src.evaluators.structured_requirement_scope_guard import (
    install_structured_requirement_scope_guard,
)

install_production_rule_scope_guard()
install_structured_requirement_scope_guard()
