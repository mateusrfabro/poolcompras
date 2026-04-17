"""Helper compartilhado para exportacao CSV com BOM UTF-8."""
import csv
from io import StringIO
from flask import Response


def csv_response(filename: str, headers: list, rows: list) -> Response:
    """Gera resposta CSV com BOM UTF-8 e delimiter ';' (Excel no Windows)."""
    buf = StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    writer.writerows(rows)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )