### 1. Mô tả chiến lược
Chiến lược được xây dựng theo hướng **Trend-Following kết hợp Momentum và Price Action**, sử dụng 3 lớp xác nhận để lọc nhiễu:
*   **Xác định xu hướng (Trend):** Sử dụng EMA nhanh (20) và EMA chậm (50). Chỉ xem xét mua khi EMA 20 > EMA 50 (xu hướng tăng) và xem xét bán/Thoát lệnh khi EMA 20 < EMA 50.
*   **Xác nhận động lượng (Momentum):** Sử dụng RSI 14 (được làm mượt bằng EMA thay vì SMA để phản ứng tốt hơn với dữ liệu intraday). Điểm mua được kích hoạt khi RSI cắt lên trên ngưỡng 50. Điểm thoát sớm được kích hoạt khi RSI suy yếu, cắt xuống dưới 45.
*   **Xác nhận hành động giá (Breakout/Breakdown):** Sử dụng kênh giá 20 phiên. Mua khi giá đóng cửa vượt đỉnh 20 phiên gần nhất (`breakout`). Thoát lệnh hoặc đảo chiều khi giá thủng đáy 20 phiên gần nhất (`breakdown`).
*   **Cơ chế vào/lệnh:** Vào lệnh (Buy) khi `trend_up` VÀ (`rsi_recover` HOẶC `breakout`). Thoát lệnh (Sell) khi `trend_down` HOẶC `momentum_fail` HOẶC `breakdown`.

### 2. Các chỉ số đạt được
Kết quả dưới đây được lấy từ notebook `test_quant.ipynb`, chạy trên mã **VIC**, khung thời gian **1H**, với `position = 100` cổ phiếu khi có tín hiệu nắm giữ.

*   **Final PnL:** -493.606 (PnL cuối kỳ sau phí).
*   **Minimum capital:** 11,553.613.
*   **Total trades:** 159 lần thay đổi trạng thái position.
*   **Win rate:** 15.01%. Lưu ý: metric này đang tính tỷ lệ ngày có lợi nhuận dương (`daily_return > 0`), không phải tỷ lệ thắng theo từng lệnh.
*   **Max drawdown:** -3,289.248.

Output kiểm tra dữ liệu lịch sử:

```text
                Datetime   Open   High    Low  Close    volume        Date      time
5095 2023-12-29 09:00:00  44.65  44.85  44.60  44.80  245400.0  2023-12-29  09:00:00
5096 2023-12-29 10:00:00  44.75  44.80  44.65  44.75  236000.0  2023-12-29  10:00:00
5097 2023-12-29 11:00:00  44.75  44.80  44.65  44.65  226100.0  2023-12-29  11:00:00
5098 2023-12-29 13:00:00  44.70  44.75  44.45  44.50  789900.0  2023-12-29  13:00:00
5099 2023-12-29 14:00:00  44.60  44.60  44.45  44.60  671500.0  2023-12-29  14:00:00
```

Output tín hiệu cuối kỳ:

```text
            Date      time  Close     rsi_14  signal  position
5095  2023-12-29  09:00:00  44.80  75.037249       1         1
5096  2023-12-29  10:00:00  44.75  73.226655       0         1
5097  2023-12-29  11:00:00  44.65  69.609021       0         1
5098  2023-12-29  13:00:00  44.50  64.464423       0         1
5099  2023-12-29  14:00:00  44.60  66.254983       0         1
```

### 3. Điểm mạnh
*   **Logic chặt chẽ, tránh mua ngược trend:** Việc bắt buộc điều kiện `trend_up` (EMA 20 > EMA 50) trước khi xét tín hiệu mua giúp chiến lược tránh được bẫy "bắt dao rơi" trong các đợt giảm mạnh.
*   **Quản lý rủi ro chủ động (Early Exit):** Điều kiện `momentum_fail` (RSI < 45) và `breakdown` cho phép chiến lược thoát lệnh sớm khi động lượng suy yếu hoặc giá phá vỡ hỗ trợ, ngay cả khi EMA chưa kịp cắt xuống. Điều này giúp bảo vệ lợi nhuận và cắt lỗ nhanh hơn so với việc chỉ đợi EMA đảo chiều.
*   **Không có lỗi Lookahead Bias:** Việc sử dụng `.shift(1)` cho `resistance_20` và `support_20` đảm bảo tín hiệu breakout/breakdown chỉ được kích hoạt dựa trên dữ liệu đã biết ở thanh nến trước đó, mô phỏng chính xác điều kiện giao dịch thực tế.
*   **Mã nguồn sạch và có khả năng mở rộng:** Cấu trúc hàm rõ ràng, tách biệt logic tính toán chỉ báo và logic sinh tín hiệu, dễ dàng tích hợp vào pipeline backtest.

### 4. Điểm yếu & rủi ro
*   **Rủi ro Overfitting trên một mã duy nhất:** Việc chỉ kiểm thử trên mã VIC khung 1H khiến kết quả có thể mang tính đặc thù (may mắn) của mã này. Chiến lược chưa được chứng minh tính bền vững (robustness) trên các mã có đặc tính thanh khoản hoặc biến động khác.
*   **Sai lệch trong cách tính Win Rate:** Đoạn code `win_rate = (daily_return > 0).mean()` tính tỷ lệ ngày thắng, không phải Trade Win Rate. Một chiến lược có thể có nhiều ngày thắng nhỏ nhưng vài lệnh thua lớn, khiến metric này không phản ánh đúng hiệu quả của từng quyết định giao dịch.
*   **Dễ bị "Whipsaw" (Cắt lỗ ảo) trong thị trường Sideway:** Khi thị trường đi ngang, EMA 20 và 50 sẽ cắt lên xuống liên tục, kết hợp với RSI dao động quanh 50, sẽ sinh ra hàng loạt tín hiệu mua/bán giả, bào mòn vốn qua phí giao dịch (slippage + commission).
*   **Thiếu Hard Stop-Loss:** Chiến lược chỉ thoát lệnh dựa trên tín hiệu kỹ thuật. Trong trường hợp thị trường gap down mạnh (tin xấu đột xuất), giá có thể thủng hỗ trợ quá sâu trước khi tín hiệu `breakdown` kịp kích hoạt, gây thiệt hại vốn lớn.

### 5. Đề xuất cải thiện
*   **Mở rộng Universe và kiểm tra Out-of-Sample:** Chạy backtest trên rổ VN30 hoặc ít nhất 10-20 mã có thanh khoản cao. Chia dữ liệu thành tập Train (ví dụ: 2020-2022) và tập Test (2023-2024) để đảm bảo chiến lược không bị overfitting.
*   **Bổ sung Hard Stop-Loss / Take-Profit dựa trên ATR:** Thêm quy tắc thoát lệnh cứng, ví dụ: Stop-loss ở mức `2 * ATR(14)` dưới giá vào lệnh, hoặc Take-profit khi đạt `3 * ATR`. Điều này giúp quản lý rủi ro độc lập với độ trễ của các chỉ báo xu hướng.
*   **Tối ưu hóa tham số (Parameter Optimization):** Sử dụng Grid Search hoặc Bayesian Optimization để tìm bộ tham số tối ưu cho `EMA_FAST`, `EMA_SLOW`, và `RSI_WINDOW`, đồng thời vẽ biểu đồ heatmap để quan sát độ nhạy của chiến lược với sự thay đổi tham số.
*   **Cải thiện hệ thống Metric:** Bổ sung các chỉ số định lượng chuyên sâu hơn vào class `Backtest_Stock` như: Trade Win Rate (số lệnh thắng / tổng lệnh), Profit Factor (Tổng lãi / Tổng lỗ), Sharpe Ratio, và Max Consecutive Losses.
*   **Lọc tín hiệu bằng Thanh khoản (Volume Filter):** Chỉ kích hoạt tín hiệu `breakout` khi khối lượng giao dịch của nến đó lớn hơn trung bình 20 phiên (`Volume > SMA(Volume, 20)`), giúp xác nhận breakout là có dòng tiền thực sự tham gia, tránh bẫy giá ảo.
