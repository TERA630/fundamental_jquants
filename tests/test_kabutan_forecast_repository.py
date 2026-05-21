from app.data.kabutan_repository import _parse_kabutan_forecast_rows, build_kabutan_forecast_snapshot, _get_kabutan_header_index


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


def test_parse_kabutan_forecast_rows_extracts_eps_and_dividend_by_header():
    html = """
    <div class="fin_year_result_d">
      <table>
        <tbody>
          <tr><th>決算期</th><th>売上高</th><th>営業益</th><th>経常益</th><th>最終益</th><th>修正1株益</th><th>配当</th></tr>
          <tr><th>2026.03予</th><td>1,200</td><td>130</td><td>120</td><td>110</td><td>65.2</td><td>24.0</td></tr>
        </tbody>
      </table>
    </div>
    """
    rows = _parse_kabutan_forecast_rows(html)
    assert rows[0].revised_eps == 65.2
    assert rows[0].dividend == 24.0


def test_parse_kabutan_forecast_rows_extracts_dividend_when_header_is_one_share_dividend():
    html = """
    <div class="fin_year_result_d">
      <table>
        <thead><tr><th>決算期</th><th>売上高</th><th>営業益</th><th>経常益</th><th>最終益</th><th><span>修正<br>1株益</span></th><th><span>修正<br>1株配</span></th></tr></thead>
        <tbody>
          <tr><th><span class="kabun1">2026.03予</span></th><td>3313018</td><td>170447</td><td>167671</td><td>114000</td><td>84.9</td><td>22</td></tr>
        </tbody>
      </table>
    </div>
    """
    rows = _parse_kabutan_forecast_rows(html)
    assert rows[0].revised_eps == 84.9
    assert rows[0].dividend == 22.0


def test_parse_kabutan_forecast_rows_supports_nested_div_structure_in_fin_year_result_block():
    html = """
    <div id="wrapper_main"><div id="container"><div id="main"><div id="finance_box">
      <div class="fin_year_t0_d">
        <div class="fin_year_result_d">
          <div class="inner-wrap">
            <table>
              <thead><tr><th>決算期</th><th>売上高</th><th>営業益</th><th>経常益</th><th>最終益</th><th>修正1株益</th><th>修正1株配</th></tr></thead>
              <tbody>
                <tr><th>2026.03予</th><td>3313018</td><td>170447</td><td>167671</td><td>114000</td><td>84.9</td><td>22</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div></div></div></div>
    """
    rows = _parse_kabutan_forecast_rows(html)
    assert len(rows) == 1
    assert rows[0].year == 2026
    assert rows[0].dividend == 22.0


def test_build_kabutan_forecast_snapshot_handles_post_earnings_layout_for_2026():
    rows = _parse_kabutan_forecast_rows(
        """
        <div class="fin_year_result_d"><table><tbody>
          <tr><th>2024.03</th><td>1000</td><td>100</td><td>95</td><td>70</td></tr>
          <tr><th>2025.03</th><td>1100</td><td>110</td><td>105</td><td>75</td></tr>
          <tr><th>2026.03</th><td>1200</td><td>130</td><td>120</td><td>90</td></tr>
          <tr><th>2027.03予</th><td>1300</td><td>140</td><td>130</td><td>95</td></tr>
        </tbody></table></div>
        """
    )
    snapshot = build_kabutan_forecast_snapshot(rows, base_year=2026)
    assert [row.year for row in snapshot.actual_rows] == [2024, 2025, 2026]
    assert [row.year for row in snapshot.forecast_rows] == [2027]


def test_build_kabutan_forecast_snapshot_handles_pre_earnings_layout_for_2026():
    rows = _parse_kabutan_forecast_rows(
        """
        <div class="fin_year_result_d"><table><tbody>
          <tr><th>2024.03</th><td>1000</td><td>100</td><td>95</td><td>70</td></tr>
          <tr><th>2025.03</th><td>1100</td><td>110</td><td>105</td><td>75</td></tr>
          <tr><th>2026.03予</th><td>1200</td><td>130</td><td>120</td><td>90</td></tr>
          <tr><th>2027.03予</th><td>1300</td><td>140</td><td>130</td><td>95</td></tr>
        </tbody></table></div>
        """
    )
    snapshot = build_kabutan_forecast_snapshot(rows, base_year=2026)
    assert [row.year for row in snapshot.actual_rows] == [2024, 2025]
    assert [row.year for row in snapshot.forecast_rows] == [2026, 2027]


def test_get_kabutan_header_index_supports_aliases():
    headers = ["決算期", "売上高", "修正1株益", "修正1株配"]
    assert _get_kabutan_header_index(headers, "revised_eps") == 2
    assert _get_kabutan_header_index(headers, "dividend") == 3
