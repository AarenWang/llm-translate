"""Table detection and extraction utilities for PDF processing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TableRegion:
    """Represents a detected table region in a PDF page."""

    x0: float
    y0: float
    x1: float
    y1: float
    rows: int
    cols: int
    confidence: float
    page_index: int = 0

    @property
    def area(self) -> float:
        return (self.x1 - self.x0) * (self.y1 - self.y0)


@dataclass
class TableCell:
    """Represents a cell in a table."""

    row: int
    col: int
    text: str
    rowspan: int = 1
    colspan: int = 1


@dataclass
class Table:
    """Represents an extracted table."""

    region: TableRegion
    cells: list[TableCell]
    headers: list[str] | None = None

    def to_markdown(self) -> str:
        """Convert table to Markdown format."""
        if not self.cells:
            return ""

        # Determine dimensions
        max_row = max(cell.row for cell in self.cells)
        max_col = max(cell.col for cell in self.cells)

        # Build grid
        grid: dict[tuple[int, int], str] = {}
        for cell in self.cells:
            for r in range(cell.row, cell.row + cell.rowspan):
                for c in range(cell.col, cell.col + cell.colspan):
                    grid[(r, c)] = cell.text

        # Generate markdown
        lines = []
        for r in range(max_row + 1):
            row_cells = [grid.get((r, c), "") for c in range(max_col + 1)]
            lines.append("| " + " | ".join(row_cells) + " |")

            # Add separator after first row (header)
            if r == 0:
                separator = "| " + " | ".join(["---"] * (max_col + 1)) + " |"
                lines.append(separator)

        return "\n".join(lines)


class TableDetector:
    """Table detection based on layout analysis."""

    def detect_tables(
        self, page_info: dict[str, Any], page_index: int = 0
    ) -> list[TableRegion]:
        """Detect tables in a PDF page."""
        tables = []

        # Method 1: Detect grid-aligned tables
        grid_tables = self._detect_grid_aligned_tables(page_info, page_index)
        tables.extend(grid_tables)

        # Method 2: Detect tables with line borders
        line_tables = self._detect_line_bordered_tables(page_info, page_index)
        tables.extend(line_tables)

        # Merge overlapping detections
        merged_tables = self._merge_overlapping_tables(tables)

        return merged_tables

    def _detect_grid_aligned_tables(
        self, page_info: dict[str, Any], page_index: int
    ) -> list[TableRegion]:
        """Detect tables by analyzing grid alignment patterns."""
        tables = []

        # Get text blocks from page
        blocks = page_info.get("blocks", [])
        if not blocks:
            return tables

        # Look for grid-like alignment patterns
        # Group blocks by y-coordinate to find rows
        rows = self._group_blocks_by_y(blocks, tolerance=10)

        # Look for consistent x-coordinate patterns (columns)
        if len(rows) >= 2:  # Need at least 2 rows to be a table
            x_positions = self._find_column_positions(rows)
            if len(x_positions) >= 2:  # Need at least 2 columns
                # Calculate table bounds
                all_x = [block["x0"] for row in rows for block in row]
                all_y = [block["y0"] for row in rows for block in row] + [
                    block["y1"] for row in rows for block in row
                ]

                if all_x and all_y:
                    tables.append(
                        TableRegion(
                            x0=min(all_x),
                            y0=min(all_y),
                            x1=max(all_x) + max(
                                block["x1"] - block["x0"] for row in rows for block in row
                            ),
                            y1=max(all_y),
                            rows=len(rows),
                            cols=len(x_positions),
                            confidence=0.7,
                            page_index=page_index,
                        )
                    )

        return tables

    def _detect_line_bordered_tables(
        self, page_info: dict[str, Any], page_index: int
    ) -> list[TableRegion]:
        """Detect tables by finding line elements (borders)."""
        tables = []

        # Check for drawing operations that look like table lines
        drawings = page_info.get("drawings", [])
        if not drawings:
            return tables

        # Look for horizontal and vertical line patterns
        horizontal_lines = [
            d for d in drawings if self._is_horizontal_line(d)
        ]
        vertical_lines = [d for d in drawings if self._is_vertical_line(d)]

        # If we have both horizontal and vertical lines, likely a table
        if len(horizontal_lines) >= 2 and len(vertical_lines) >= 2:
            # Estimate table region
            y_coords = [line["y0"] for line in horizontal_lines]
            x_coords = [line["x0"] for line in vertical_lines]

            if y_coords and x_coords:
                tables.append(
                    TableRegion(
                        x0=min(x_coords),
                        y0=min(y_coords),
                        x1=max(x_coords) + max(
                            line.get("width", 0) for line in vertical_lines
                        ),
                        y1=max(y_coords) + max(
                            line.get("height", 0) for line in horizontal_lines
                        ),
                        rows=len(horizontal_lines),
                        cols=len(vertical_lines),
                        confidence=0.9,  # Higher confidence for bordered tables
                        page_index=page_index,
                    )
                )

        return tables

    def extract_table_structure(
        self, region: TableRegion, blocks: list[dict[str, Any]]
    ) -> Table:
        """Extract table structure from a table region."""
        # Filter blocks within the table region
        table_blocks = [
            block
            for block in blocks
            if self._is_block_in_region(block, region)
        ]

        if not table_blocks:
            return Table(region=region, cells=[])

        # Analyze grid structure
        rows = self._group_blocks_by_y(table_blocks, tolerance=8)
        cols = self._group_blocks_by_x(table_blocks, tolerance=8)

        # Create cells
        cells = []
        for row_idx, row in enumerate(rows):
            for col_idx, block in enumerate(row):
                if block:
                    cells.append(
                        TableCell(
                            row=row_idx, col=col_idx, text=block.get("text", "").strip()
                        )
                    )

        # Detect header row (first row)
        headers = None
        if cells:
            header_cells = [cell for cell in cells if cell.row == 0]
            headers = [cell.text for cell in header_cells]

        return Table(region=region, cells=cells, headers=headers)

    def _group_blocks_by_y(
        self, blocks: list[dict[str, Any]], tolerance: float = 10
    ) -> list[list[dict[str, Any]]]:
        """Group blocks by y-coordinate (rows)."""
        if not blocks:
            return []

        # Sort by y-coordinate
        sorted_blocks = sorted(blocks, key=lambda b: b.get("y0", 0))

        rows = []
        current_row = [sorted_blocks[0]]
        current_y = sorted_blocks[0].get("y0", 0)

        for block in sorted_blocks[1:]:
            block_y = block.get("y0", 0)
            if abs(block_y - current_y) <= tolerance:
                current_row.append(block)
            else:
                rows.append(current_row)
                current_row = [block]
                current_y = block_y

        if current_row:
            rows.append(current_row)

        return rows

    def _group_blocks_by_x(
        self, blocks: list[dict[str, Any]], tolerance: float = 10
    ) -> list[list[dict[str, Any]]]:
        """Group blocks by x-coordinate (columns)."""
        if not blocks:
            return []

        # Sort by x-coordinate
        sorted_blocks = sorted(blocks, key=lambda b: b.get("x0", 0))

        cols = []
        current_col = [sorted_blocks[0]]
        current_x = sorted_blocks[0].get("x0", 0)

        for block in sorted_blocks[1:]:
            block_x = block.get("x0", 0)
            if abs(block_x - current_x) <= tolerance:
                current_col.append(block)
            else:
                cols.append(current_col)
                current_col = [block]
                current_x = block_x

        if current_col:
            cols.append(current_col)

        return cols

    def _find_column_positions(self, rows: list[list[dict[str, Any]]]) -> list[float]:
        """Find consistent column x-positions across rows."""
        if not rows:
            return []

        # Collect all x-positions
        all_x = []
        for row in rows:
            for block in row:
                all_x.append(block.get("x0", 0))

        if not all_x:
            return []

        # Cluster x-positions (simple version: sort and group)
        sorted_x = sorted(all_x)
        clusters = []

        for x in sorted_x:
            if not clusters or abs(x - clusters[-1]) > 20:  # Threshold for new column
                clusters.append(x)

        return clusters

    def _is_horizontal_line(self, drawing: dict[str, Any]) -> bool:
        """Check if drawing is a horizontal line."""
        width = drawing.get("width", 0)
        height = drawing.get("height", 0)
        return width > height * 3 and height < 5

    def _is_vertical_line(self, drawing: dict[str, Any]) -> bool:
        """Check if drawing is a vertical line."""
        width = drawing.get("width", 0)
        height = drawing.get("height", 0)
        return height > width * 3 and width < 5

    def _is_block_in_region(
        self, block: dict[str, Any], region: TableRegion
    ) -> bool:
        """Check if block is within table region."""
        block_x = block.get("x0", 0)
        block_y = block.get("y0", 0)

        return (
            region.x0 <= block_x <= region.x1
            and region.y0 <= block_y <= region.y1
        )

    def _merge_overlapping_tables(
        self, tables: list[TableRegion]
    ) -> list[TableRegion]:
        """Merge overlapping table detections."""
        if not tables:
            return []

        # Sort by confidence (descending)
        sorted_tables = sorted(tables, key=lambda t: t.confidence, reverse=True)

        merged = [sorted_tables[0]]

        for table in sorted_tables[1:]:
            overlap_found = False
            for existing in merged:
                if self._tables_overlap(table, existing):
                    # Keep the one with higher confidence
                    if table.confidence > existing.confidence:
                        merged.remove(existing)
                        merged.append(table)
                    overlap_found = True
                    break

            if not overlap_found:
                merged.append(table)

        return merged

    def _tables_overlap(
        self, table1: TableRegion, table2: TableRegion, threshold: float = 0.5
    ) -> bool:
        """Check if two table regions overlap."""
        # Calculate intersection
        x_overlap = max(0, min(table1.x1, table2.x1) - max(table1.x0, table2.x0))
        y_overlap = max(0, min(table1.y1, table2.y1) - max(table1.y0, table2.y0))
        overlap_area = x_overlap * y_overlap

        # Check if overlap is significant
        min_area = min(table1.area, table2.area)
        return min_area > 0 and overlap_area / min_area > threshold
