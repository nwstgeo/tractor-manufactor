"""
H: Hardware Failure & Material Availability & Spare Reqs (net-need arithmetic).
"""


def spares(demand: float,
           mean_failure: float,
           base_buffer: float = 0.10,
           failure_weight: float = 2.0) -> int:
    """
    Compute spare-part buffer in whole tractor-equivalent units.

    Args:
        demand: planned demand in tractor units.
        mean_failure: average part failure rate across the event's parts.
        base_buffer: flat safety fraction of demand.
        failure_weight: extra buffer per unit of failure rate.

    Returns:
        Rounded spare quantity as int.
    """
    return round(demand * (base_buffer + failure_weight * mean_failure))


def net_need(plan: float,
             backlog: float,
             spare_qty: float,
             on_hand: float,
             on_order: float) -> float:
    """
    Compute net order need: gross requirement minus available position.

    Args:
        plan: planned builds.
        backlog: unfilled tractor backlog.
        spare_qty: failure-driven spare buffer.
        on_hand: stock on hand.
        on_order: stock already inbound.

    Returns:
        Non-negative net quantity to order.
    """
    return max(0, plan + backlog + spare_qty - on_hand - on_order)


def limiting_part(inventory_by_part: dict) -> str:
    """
    Identify the bottleneck part (lowest on-hand stock).

    Args:
        inventory_by_part: dict mapping Part_SKU to on-hand quantity.

    Returns:
        Part_SKU with the minimum quantity.
    """
    return min(inventory_by_part, key=inventory_by_part.get)


def rank_suppliers(supplier_delay_p50: dict,
                   supplier_unit_cost: dict) -> list:
    """
    Rank suppliers best-first by delay, breaking ties on unit cost.

    Args:
        supplier_delay_p50: dict supplier -> median delay in days.
        supplier_unit_cost: dict supplier -> representative unit cost.

    Returns:
        Supplier names sorted best-first.
    """
    return sorted(supplier_delay_p50,
                  key=lambda s: (supplier_delay_p50[s], supplier_unit_cost.get(s, 0)))
