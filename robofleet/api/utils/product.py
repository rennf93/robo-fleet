"""
Product Route Helpers

Route-glue helpers backing robofleet/api/routes/product.py.
"""

from robofleet.models.product import ProductCellMapping


def to_mappings(cells: list) -> list[ProductCellMapping]:
    return [ProductCellMapping(team=c.team, project_id=c.project_id) for c in cells]
