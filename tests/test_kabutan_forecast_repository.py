from app.data.kabutan_repository import _parse_kabutan_forecast_rows


def test_parse_kabutan_forecast_rows_extracts_actual_and_forecast_rows():
    html = """
    <div class="fin_year_result_d">
      <table>
        <tbody>
          <tr><th>2025.03</th><td>1,000</td><td>100</td><td>90</td><td>80</td></tr>
          <tr><th>2026.03予</th><td>1,200</td><td>130</td><td>120</td><td>110</td></tr>
          <tr><th>2027.03予</th><td>1,350</td><td>150</td><td>140</td><td>120</td></tr>
        </tbody>
      </table>
    </div>
    """

    rows = _parse_kabutan_forecast_rows(html)

    assert len(rows) == 3
    assert rows[0].section == "実績"
    assert rows[1].section == "予想"
    assert rows[1].year == 2026
    assert rows[1].sales == 1200
    assert rows[2].year == 2027
