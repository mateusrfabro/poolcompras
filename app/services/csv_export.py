"""Helper compartilhado para exportacao CSV com BOM UTF-8."""
import csv
from io import StringIO
from flask import Response


def csv_response(filename: str, headers: list, rows: list, delimiter: str = ";") -> Response:
    """Gera resposta CSV com BOM UTF-8. Delimiter default ';' (Excel BR)."""
    buf = StringIO()
    buf.write("﻿")
    writer = csv.writer(buf, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    writer.writerows(rows)
    return Response(
        buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
