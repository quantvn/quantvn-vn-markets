# QuantVN - Python Library for Vietnamese Financial Market Analysis

**QuantVN** là thư viện Python toàn diện cho phân tích định lượng và truy xuất dữ liệu tài chính, được tối ưu hóa đặc biệt cho thị trường tài chính Việt Nam và cryptocurrency.

## Tính năng nổi bật

**Hoàn toàn miễn phí & mã nguồn mở**: Dễ dàng truy cập và sử dụng cho cá nhân, nhà phân tích định lượng, và cộng đồng nghiên cứu.

**Giải pháp Python toàn diện**: API đơn giản, dễ tích hợp vào hệ thống giao dịch tự động.

**Dữ liệu thị trường**:

- Cổ phiếu Việt Nam (HOSE, HNX, UPCOM)
- Phái sinh VN30

**Công cụ phân tích mạnh mẽ**: Tích hợp sẵn các chỉ số hiệu suất, backtesting, và đánh giá rủi ro.

## Quy trình QuantVN

Để xây dựng một hệ thống giao dịch thành công, QuantVN vận hành theo một quy trình 4 bước khép kín và logic.

![image](https://res.cloudinary.com/dbn4eimis/image/upload/v1773975369/image_1_pxtcuk.png)

## Cài đặt

### Từ PyPI (khuyến nghị)

```bash
pip install quantvn
```

### Từ mã nguồn

```bash
git clone https://github.com/your-repo/quantvn.git
cd quantvn
pip install -e .
```

### Yêu cầu hệ thống

- Python >= 3.9
- pandas
- requests
- matplotlib
- tqdm

## Bắt đầu nhanh

### Khởi tạo API Client

Để sử dụng các tính năng của QuantVN , người dùng cần cung cấp API Key được cấp từ nền tảng **QuantVN** | https://quantvn.com/.

<p align="center">
  <img src="https://res.cloudinary.com/dbn4eimis/image/upload/v1773975781/Gemini_Generated_Image_r5fls6r5fls6r5fl_ktk5hx.png
" alt="QuantVN" width="300"/>
</p>

<p align="center">
  <a href="https://quantvn.com/">
    <img src="https://img.shields.io/badge/🌐 Visit Website-QuantVN-blue?style=for-the-badge" />
  </a>
</p>

API Key được sử dụng để xác thực các yêu cầu tới hệ thống dữ liệu của QuantVN, giúp kiểm soát truy cập, đảm bảo tính ổn định của dịch vụ và theo dõi mức sử dụng.

```python
from quantvn.vn.data.utils import client

# Khởi tạo với API key (nếu có)
client(apikey="your_api_key_here")
```

**Lưu ý**: Một số chức năng có thể hoạt động mà không cần API key, nhưng khuyến nghị có API key để truy cập đầy đủ.

---

## Tài liệu API

### 1. Dữ liệu Cổ phiếu Việt Nam

Module: `quantvn.vn.data`

#### 1.1. Danh sách cổ phiếu thanh khoản cao

```python
from quantvn import client
client(apikey="your_api_key_here")

from quantvn.vn.data import list_liquid_asset

# Lấy danh sách cổ phiếu có thanh khoản cao
liquid_stocks = list_liquid_asset()
print(liquid_stocks.head())
```

**Output:**

```python
  symbol      liquidity
0    VCB   5.234567e+10
1    HPG   4.123456e+10
2    VIC   3.876543e+10
```

#### 1.2. Dữ liệu lịch sử cổ phiếu

```python
from quantvn.vn.data import get_stock_hist

# Lấy dữ liệu 1H (ví dụ sử dụng khung giờ 1H)
vic_hour = get_stock_hist("VIC", resolution="1H")
print(vic_hour.head())
```

**Tham số:**

- `symbol` (str): Mã cổ phiếu (VD: "VIC", "HPG", "VCB")
- `resolution` (str): Khung thời gian, hiện chỉ hỗ trợ `"1H"` (bắt buộc).

**Output:**

```python
        Date      time   Open   High    Low  Close      volume
0 2024-01-02  09:00:00  42.50  42.80  42.30  42.60  1234567.0
1 2024-01-02  10:00:00  42.60  42.90  42.50  42.75  2345678.0
```

#### 1.3. Thông tin chi tiết công ty

```python
from quantvn import client
client(apikey="your_api_key_here")

from quantvn.vn.data import Company

company = Company("VIC")

# Thông tin tổng quan
overview = company.overview()
print("Thông tin tổng quan")
print(overview[["symbol", "id", "issue_share", "icb_name2", "icb_name4"]])

# Danh sách cổ đông
shareholders = company.shareholders()
print("Danh sách cổ đông")
print(shareholders.head())

# Ban lãnh đạo
officers = company.officers()
print("Ban lãnh đạo")
print(officers.head())

# Công ty con
subsidiaries = company.subsidiaries()
print("Công ty con")
print(subsidiaries.head())

# Sự kiện quan trọng
events = company.events()
print("Sự kiện quan trọng")
print(events.head())

# Tin tức
news = company.news()
print("Tin tức")
print(news.head())

# Tỷ số tài chính tổng hợp
ratios = company.ratio_summary()
print("Tỷ số tài chính tổng hợp")
print(ratios[["pe", "pb", "roe", "roa"]])
```

**Output:**

```python
Thông tin tổng quan
  symbol     id  issue_share     icb_name2     icb_name4
0    VIC  76055   7706031024  Bất động sản  Bất động sản

Danh sách cổ đông
          id ticker  ...     updateDate                __typename
0  100950872    VIC  ...  1770048564380  OrganizationShareHolders
1  100950031    VIC  ...  1767201363047  OrganizationShareHolders
2  100971726    VIC  ...  1767201489503  OrganizationShareHolders
3  100972520    VIC  ...  1770048733047  OrganizationShareHolders
4  100950463    VIC  ...  1770048609397  OrganizationShareHolders

Ban lãnh đạo
   id ticker          fullName  ... percentage   quantity           __typename
0  19    VIC   Phạm Nhật Vượng  ...   0.091010  703848781  OrganizationManager
1   5    VIC    Phạm Thu Hương  ...   0.044280  341221050  OrganizationManager
2   6    VIC    Phạm Thúy Hằng  ...   0.029630  228326892  OrganizationManager
3   4    VIC   Phạm Văn Khương  ...   0.000600    2267587  OrganizationManager
4  18    VIC  Nguyễn Diệu Linh  ...   0.000242    1865418  OrganizationManager

Công ty con
         id organCode subOrganCode  percentage                                   subOrListingInfo  __typename
0  28590324       VIC   0110006565      0.6142  {'enOrganName': 'VS Development Investment Joi...  Subsidiary
1  28590325       VIC   0110009975         NaN  {'enOrganName': 'Vincom Retail Investment Join...  Subsidiary
2  28590326       VIC   0110537975      0.6581  {'enOrganName': 'SV Tay Hanoi Real Estate Join...  Subsidiary
3  28590327       VIC   0110873550      0.7339  {'enOrganName': 'Vinhomes Ha Tinh Industrial Z...  Subsidiary
4  28590328       VIC   0110873568      0.7305  {'enOrganName': 'Vinhomes Hai Phong Industrial...  Subsidiary

Sự kiện quan trọng
      id organCode ticker                                  eventTitle  ...    exrightDate  eventListName    en_EventListName         __typename
0  34642       VIC    VIC                               Niêm yết thêm  ... -6847804800000  Niêm yết thêm  Additional Listing  OrganizationEvent
1  34686       VIC    VIC                               Niêm yết thêm  ... -6847804800000  Niêm yết thêm  Additional Listing  OrganizationEvent
2  34687       VIC    VIC                               Niêm yết thêm  ... -6847804800000  Niêm yết thêm  Additional Listing  OrganizationEvent
3  34702       VIC    VIC  VIC-Niêm yết bổ sung 484.473.162 cổ phiếu   ... -6847804800000  Niêm yết thêm  Additional Listing  OrganizationEvent
4  34657       VIC    VIC                               Niêm yết thêm  ... -6847804800000  Niêm yết thêm  Additional Listing  OrganizationEvent

Tin tức
        id organCode ticker                                          newsTitle newsSubTitle  ... referencePrice floorPrice ceilingPrice percentPriceChange  __typename
0  9588803       VIC    VIC  VIC: Nghị quyết HĐQT về việc niêm yết trái phi...               ...       145000.0   134900.0     155100.0          -0.002759        News
1  9559000       VIC    VIC  VIC: Thông báo giao dịch cổ phiếu của tổ chức ...               ...       141800.0   131900.0     151700.0           0.029619        News
2  9515973       VIC    VIC  VIC: Thông báo về ngày đăng ký cuối cùng để th...               ...       164800.0   153300.0     176300.0          -0.050364        News
3  9479016       VIC    VIC  VIC: Quyết định về việc chốt danh sách người s...               ...       168900.0   157100.0     180700.0           0.018354        News
4  9469700       VIC    VIC             VIC: CBTT phát hành trái phiếu quốc tế               ...       168900.0   157100.0     180700.0           0.018354        News

Tỷ số tài chính tổng hợp
         pe        pb      roe       roa
0  83.96933  7.596341  0.09402  0.013734
```

#### 1.4. Tỷ số tài chính

```python
from quantvn import client
client(apikey="your-apikey-here")

from quantvn.vn.data import Finance

# Khởi tạo Finance (dùng BACKEND mặc định)
finance = Finance("HPG")

# Tỷ số tài chính theo quý
ratios_q = finance.ratio(period="Q")
print("Tỷ số tài chính theo quý:")
if not ratios_q.empty:
    print(ratios_q[["year", "quarter", "revenue", "netProfit", "roe", "pe", "pb"]].head())

# Tỷ số tài chính theo năm
ratios_y = finance.ratio(period="Y")
print("\nTỷ số tài chính theo năm:")
if not ratios_y.empty:
    print(ratios_y[["year", "revenue", "netProfit", "roe", "pe", "pb"]].head())
```

**Output:**

```python
Tỷ số tài chính theo quý:
   year  year  quarter  quarter         revenue      netProfit       roe         pe        pb
0  2025  2025        4        4  47301623136340  3860994446656  0.126882  13.314004  1.592397
1  2025  2025        3        3  36793873449413  3988318474539  0.120224  14.527037  1.667413
2  2025  2025        2        2  36286185846409  4256487211764  0.115502  16.199640  1.790441
3  2025  2025        1        1  37950635502050  3344284694388  0.110522  15.817610  1.679199
4  2024  2024        4        4  35232197602514  2808645369171  0.110732  13.754011  1.445857

Tỷ số tài chính theo năm:
   year  year          revenue       netProfit       roe         pe        pb
0  2025  2025  158332317934212  15450084827347  0.126882  13.314004  1.592397
1  2024  2024  140561387448572  12021443836074  0.110732  14.344970  1.476620
2  2023  2023  120355231616139   6835064334356  0.068771  23.858738  1.507863
3  2022  2022  142770810676858   8483510554031  0.090911  19.253321  1.692821
4  2021  2021  150865359967200  34478143197460  0.459707   2.407519  0.888407
```

**Tham số:**

- `period` (str): `"Q"` (quý) hoặc `"Y"` (năm)
- `dropna` (bool): Loại bỏ các giá trị null (mặc định: `False`)

#### 1.5. Dữ liệu Quote realtime

```python
from quantvn.vn.data import Quote

quote = Quote("ACB")

# Lấy dữ liệu lịch sử trong khoảng thời gian
history = quote.history(
    start="2024-01-01",
    end="2024-03-31",
    interval="1D"
)
print("Dữ liệu lịch sử trong khoảng thời gian")
print(history.head())

# Dữ liệu tick intraday
intraday = quote.intraday(page_size=200)
print("Dữ liệu tick intraday")
print(intraday.head())

# Độ sâu thị trường (price depth)
depth = quote.price_depth()
print("Độ sâu thị trường (price depth)")
print(depth.head())
```

**Output:**

```python
Dữ liệu lịch sử trong khoảng thời gian
        time      open      high       low     close    volume
0 2024-01-02  16808.59  17370.04  16808.59  17159.50  13896933
1 2024-01-03  17194.59  17545.50  17019.13  17545.50   9817807
2 2024-01-04  17685.86  18001.68  17615.68  17756.05  23605373
3 2024-01-05  17756.05  17861.32  17580.59  17861.32   9282598
4 2024-01-08  18036.77  18071.87  17685.86  17791.14  12398885

Dữ liệu tick intraday
                 time    price  volume match_type         id
0 2026-03-19 06:26:22  23300.0  1300.0          s  452011243
1 2026-03-19 06:26:22  23300.0   200.0          s  452011242
2 2026-03-19 06:26:22  23300.0   100.0          s  452011241
3 2026-03-19 06:26:22  23300.0   400.0          s  452011240
4 2026-03-19 06:26:21  23350.0   100.0          b  452011220

Độ sâu thị trường (price depth)
     price acc_volume acc_buy_volume acc_sell_volume acc_undefined_volume
0  23550.0    32800.0        21300.0         11500.0                  0.0
1  23500.0   627100.0       357900.0          7400.0             261800.0
2  23450.0  2006100.0      1413700.0        592400.0                  0.0
3  23400.0  1724200.0       655300.0       1068900.0                  0.0
4  23350.0  1214700.0       569600.0        645100.0                  0.0
```

#### 1.6. Thông tin giao dịch

```python
from quantvn.vn.data import Trading

# Bảng giá nhiều mã cùng lúc
price_board = Trading.price_board(["VCB", "ACB", "TCB"])
print(price_board)
```

**Output:**

```python
  symbol  open ceiling floor  ref_price  high   low  price_change  price_change_pct foreign_volume foreign_room foreign_holding_room avg_match_volume_2w
0    VCB  None    None  None    60500.0  None  None       -1400.0         -2.314050           None         None                 None                None
1    ACB  None    None  None    23750.0  None  None        -450.0         -1.894737           None         None                 None                None
2    TCB  None    None  None    30300.0  None  None        -350.0         -1.155116           None         None                 None                None
```

#### 1.7. Quỹ mở

```python
from quantvn.vn.data import Fund

fund = Fund()

# Danh sách tất cả quỹ
all_funds = fund.listing()
print("Danh sách tất cả quỹ")
print(all_funds.head())

# Lọc theo loại quỹ
stock_funds = fund.listing(fund_type="STOCK")    # Quỹ cổ phiếu
bond_funds = fund.listing(fund_type="BOND")      # Quỹ trái phiếu
balanced_funds = fund.listing(fund_type="BALANCED")  # Quỹ cân bằng

print("Quỹ cổ phiếu:")
print(stock_funds[["name", "code", "nav"]].head())

# Tìm kiếm quỹ theo tên
search_result = fund.filter("RVPIF")
print("Tìm kiếm quỹ theo tên")
print(search_result)
```

**Output:**

```python
Danh sách tất cả quỹ
   id                                              name shortName   code  ... productNavChange.updateAt extra.lastNAVDate extra.lastNAV  extra.currentNAV
0  38                           QUỸ ĐẦU TƯ CHỦ ĐỘNG VND     VNDAF  VNDAF  ...             1773901367003     1773853200000      19974.77          19974.77
1  80  QUỸ ĐẦU TƯ CỔ PHIẾU CỔ TỨC NĂNG ĐỘNG VINACAPITAL      VDEF   VDEF  ...             1773894131379     1773766800000      12475.45          12475.45
2  21       QUỸ ĐẦU TƯ TRÁI PHIẾU BẢO THỊNH VINACAPITAL       VFF    VFF  ...             1773894123666     1773680400000      25857.51          25857.51
3  37                         QUỸ ĐẦU TƯ TRÁI PHIẾU VND     VNDBF  VNDBF  ...             1773894901858     1773853200000      15770.78          15770.78
4  41   QUỸ ĐẦU TƯ CỔ PHIẾU TĂNG TRƯỞNG BALLAD VIỆT NAM      TBLF   TBLF  ...             1773894127776     1773680400000      11281.69          11281.69

Quỹ cổ phiếu:
                                                name     code       nav
0                            QUỸ ĐẦU TƯ CHỦ ĐỘNG VND    VNDAF  19974.77
1   QUỸ ĐẦU TƯ CỔ PHIẾU CỔ TỨC NĂNG ĐỘNG VINACAPITAL     VDEF  12475.45
2    QUỸ ĐẦU TƯ CỔ PHIẾU TĂNG TRƯỞNG BALLAD VIỆT NAM     TBLF  11281.69
3  QUỸ ĐẦU TƯ CỔ PHIẾU TĂNG TRƯỞNG MIRAE ASSET VI...    MAGEF  21768.81
4                  QUỸ ĐẦU TƯ THU NHẬP CHỦ ĐỘNG VCBF  VCBFAIF  11613.50

Tìm kiếm quỹ theo tên
    id                              name shortName    code  ... productNavChange.updateAt extra.lastNAVDate extra.lastNAV  extra.currentNAV
55  83  QUỸ ĐẦU TƯ THỊNH VƯỢNG RỒNG VIỆT     RVPIF  RVPF24  ...             1773894120943     1773766800000      10881.64          10881.64
```

#### 1.8. Danh sách mã chứng khoán

```python
from quantvn.vn.data import Listing

listing = Listing()

# Lấy danh sách mã theo sàn
symbols = listing.symbols_by_exchange()
print(f"HOSE: {len(symbols['HOSE'])} symbols")
print(f"HNX: {len(symbols['HNX'])} symbols")
print(f"UPCOM: {len(symbols['UPCOM'])} symbols")
```

**Output:**

```python
HOSE: 3 symbols
HNX: 0 symbols
UPCOM: 0 symbols
```

---

### 2. Phái sinh VN30

```python
from quantvn import client
client(apikey="your-apikey-here")

from quantvn.vn.data import get_derivatives_hist

# Dữ liệu VN30F1M theo phút
vn30_1m = get_derivatives_hist("VN30F1M", "1m")
print("Dữ liệu VN30F1M theo phút")
print(vn30_1m.head())

# Dữ liệu VN30F1M theo 5 phút
vn30_5m = get_derivatives_hist("VN30F1M", "5m")
print("Dữ liệu VN30F1M theo 5 phút")
print(vn30_5m.head())

# Dữ liệu VN30F1M theo 15 phút
vn30_15m = get_derivatives_hist("VN30F1M", "15m")
print("Dữ liệu VN30F1M theo 15 phút")
print(vn30_15m.head())

# Các resolution hỗ trợ: "1m", "5m", "15m"
```

**Output:**

```python
Dữ liệu VN30F1M theo phút
         Date      time   Open   High    Low  Close  volume            Datetime
0  2018-08-13  09:01:00  943.0  943.1  942.9  943.1   220.0 2018-08-13 09:01:00
1  2018-08-13  09:02:00  943.0  943.6  943.0  943.5   121.0 2018-08-13 09:02:00
2  2018-08-13  09:03:00  943.3  943.4  943.3  943.4   135.0 2018-08-13 09:03:00
3  2018-08-13  09:04:00  943.2  943.2  943.0  943.1   361.0 2018-08-13 09:04:00
4  2018-08-13  09:05:00  943.1  943.1  942.9  943.0   343.0 2018-08-13 09:05:00

Dữ liệu VN30F1M theo 5 phút
         Date      time   Open   High    Low  Close  volume            Datetime
0  2018-08-13  09:00:00  943.5  943.6  942.9  943.1  1812.0 2018-08-13 09:00:00
1  2018-08-13  09:05:00  943.1  943.5  942.9  943.3  1323.0 2018-08-13 09:05:00
2  2018-08-13  09:10:00  943.2  943.3  942.6  943.1  1207.0 2018-08-13 09:10:00
3  2018-08-13  09:15:00  943.1  943.1  942.3  942.6  1196.0 2018-08-13 09:15:00
4  2018-08-13  09:20:00  942.6  943.7  942.4  943.7  1765.0 2018-08-13 09:20:00

Dữ liệu VN30F1M theo 15 phút
         Date      time   Open   High    Low  Close  volume            Datetime
0  2018-08-13  09:00:00  943.5  943.6  942.6  943.1  4342.0 2018-08-13 09:00:00
1  2018-08-13  09:15:00  943.1  945.9  942.3  945.3  5430.0 2018-08-13 09:15:00
2  2018-08-13  09:30:00  945.2  945.5  943.3  944.5  4933.0 2018-08-13 09:30:00
3  2018-08-13  09:45:00  944.5  946.4  944.3  946.0  4254.0 2018-08-13 09:45:00
4  2018-08-13  10:00:00  945.9  946.3  944.5  945.2  4336.0 2018-08-13 10:00:00
```

---

---

### 3. Technical Analysis & Fundamental Features

#### 3.1. Thêm chỉ báo kỹ thuật

```python
from quantvn.vn.data import add_all_ta_features, get_stock_hist

# Lấy dữ liệu
df = get_stock_hist("VIC", resolution="1H")

# Thêm tất cả chỉ báo kỹ thuật
df_with_ta = add_all_ta_features(df)

# DataFrame sẽ có thêm các cột: RSI, MACD, Bollinger Bands, etc.
print(df_with_ta.columns)
print(df_with_ta.head())
```

**Output:**

```python
['Date', 'time', 'Open', 'High', 'Low', 'Close', 'volume', 'volume_adi', 'volume_obv', 'volume_cmf',...'sma_fast', 'sma_slow', 'ema_fast',
'ema_slow', 'bb_middle', 'bb_high','bb_low', 'bb_width', 'bb_percent', 'atr']

Date      time   Open   High    Low  Close     volume  ...   ema_slow  bb_middle    bb_high     bb_low  bb_width  bb_percent  atr
0  2023-03-20  09:00:00  26.50  26.60  26.20  26.30   188600.0  ...  26.300000    26.3000  26.300000  26.300000  0.000000    0.000000  0.0
1  2023-03-20  10:00:00  26.25  26.40  26.00  26.10   319300.0  ...  26.285185    26.2000  26.400000  26.000000  1.526718    0.250000  0.0
2  2023-03-20  11:00:00  26.05  26.10  25.85  25.90   294700.0  ...  26.256653    26.1000  26.426599  25.773401  2.502672    0.193814  0.0
3  2023-03-20  13:00:00  25.90  25.95  25.70  25.75   928800.0  ...  26.219123    26.0125  26.427078  25.597922  3.187530    0.183413  0.0
4  2023-03-20  14:00:00  25.80  26.40  25.70  26.40  1630900.0  ...  26.232521    26.0900  26.573322  25.606678  3.705035    0.820697  0.0
```

#### 3.2. Thêm chỉ số tài chính cơ bản

```python
from quantvn.vn.data import add_all_fund_features, get_stock_hist

# Lấy dữ liệu
df = get_stock_hist("HPG", resolution="1H")

# Thêm các chỉ số tài chính (PE, PB, ROE, ROA, etc.)
df_with_fund = add_all_fund_features(df, symbol="HPG")

print(df_with_fund.columns)
print(df_with_fund.head())
```

**Output:**

```python
['Date', 'time', 'Open', 'High', 'Low', 'Close', 'volume', 'ticker','year', 'quarter']

        Date      time   Open   High    Low  Close     volume ticker  year  quarter
0 2023-03-20  09:00:00  15.46  15.61  15.37  15.57  3598400.0    HPG  2023        1
1 2023-03-20  10:00:00  15.61  15.61  15.42  15.49  3128900.0    HPG  2023        1
2 2023-03-20  11:00:00  15.49  15.49  15.37  15.42  1437100.0    HPG  2023        1
3 2023-03-20  13:00:00  15.42  15.42  15.19  15.22  7626000.0    HPG  2023        1
4 2023-03-20  14:00:00  15.22  15.30  15.15  15.15  7198500.0    HPG  2023        1
```

#### 3.3. Lấy từng chỉ số cụ thể

```python
from quantvn import client
client(apikey="your-apikey-here")

from quantvn.vn.data import fund_feature

# Lấy ROE
roe_data = fund_feature("roe", "VCB")
print(roe_data.head())

```

**Output:**

```python
         Date      time   Open   High    Low  Close    Volume  roe
0  2023-03-20  09:00:00  50.04  50.32  49.77  50.04  189400.0  NaN
1  2023-03-20  10:00:00  50.04  50.04  49.54  49.65  170900.0  NaN
2  2023-03-20  11:00:00  49.65  49.71  49.48  49.48  115500.0  NaN
3  2023-03-20  13:00:00  49.48  49.59  48.86  48.92  189800.0  NaN
4  2023-03-20  14:00:00  48.92  49.15  47.85  47.85  367000.0  NaN
```

**Các chỉ số khả dụng:**

- `earningPerShare` (EPS)
- `bookValuePerShare` (BVPS)
- `roe` (Return on Equity)
- `roa` (Return on Assets)
- `priceToEarning` (P/E)
- `priceToBook` (P/B)
- Và nhiều chỉ số khác...

---

### 4. Backtesting & Performance Analysis

#### 4.1. Backtest cho phái sinh

```python
from quantvn import client
client(apikey="your-apikey-here")

from quantvn.vn.metrics import Backtest_Derivates
from quantvn.vn.data import get_derivatives_hist
import pandas as pd

# Lấy dữ liệu
df = get_derivatives_hist("VN30F1M", "5m")

# Tạo tín hiệu giao dịch đơn giản (ví dụ: MA crossover)
df["ma_short"] = df["Close"].rolling(20).mean()
df["ma_long"] = df["Close"].rolling(50).mean()

# Position: 1 (long), -1 (short), 0 (no position)
df["position"] = 0
df.loc[df["ma_short"] > df["ma_long"], "position"] = 1
df.loc[df["ma_short"] < df["ma_long"], "position"] = -1
print(df.iloc[100:105])

# Chạy backtest (PnL sau phí)
backtest = Backtest_Derivates(df, pnl_type="after_fees")

# Xem PnL tích lũy
pnl = backtest.PNL()
print(f"Final PnL: {pnl.iloc[-1]:,.2f} VND")

# PnL theo ngày
daily_pnl = backtest.daily_PNL()
print(daily_pnl.tail())

# Ước tính vốn tối thiểu
min_capital = backtest.estimate_minimum_capital()
print(f"Minimum capital needed: {min_capital:,.0f} VND")

# Vẽ biểu đồ PnL
backtest.plot_PNL("VN30F1M - MA Crossover Strategy")
```

**Output**

```python
           Date      time   Open   High    Low  Close  volume            Datetime  ma_short  ma_long  position
100  2018-08-15  09:10:00  959.3  960.5  959.3  960.4   927.0 2018-08-15 09:10:00   958.645  956.424         1
101  2018-08-15  09:15:00  960.3  961.1  960.3  960.7  1413.0 2018-08-15 09:15:00   958.930  956.538         1
102  2018-08-15  09:20:00  960.8  960.8  960.1  960.3  1172.0 2018-08-15 09:20:00   959.135  956.606         1
103  2018-08-15  09:25:00  960.3  960.3  959.0  959.0  1735.0 2018-08-15 09:25:00   959.290  956.670         1
104  2018-08-15  09:30:00  959.3  960.1  959.2  960.1  1271.0 2018-08-15 09:30:00   959.460  956.762         1

Final PnL: 1,783.93 VND

2022-12-26    1809.1830
2022-12-27    1823.1290
2022-12-28    1816.6955
2022-12-29    1794.6620
2022-12-30    1783.9285

Minimum capital needed: 980 VND
```

**Tham số:**

- `pnl_type` (str):
  - `"raw"`: PnL thô (chưa trừ phí)
  - `"after_fees"`: PnL sau khi trừ phí giao dịch

#### 4.2. Backtest cho cổ phiếu

```python
from quantvn.vn.metrics import Backtest_Stock
from quantvn.vn.data import get_stock_hist

# Lấy dữ liệu
df = get_stock_hist("VIC", resolution="1H")

# Tạo chiến lược đơn giản
df["ma20"] = df["Close"].rolling(20).mean()
df["ma50"] = df["Close"].rolling(50).mean()

# Position: số lượng cổ phiếu (ví dụ: 100 cổ)
df["position"] = 0
df.loc[df["ma20"] > df["ma50"], "position"] = 100
print(df.iloc[100:105])

# Backtest
backtest = Backtest_Stock(df, pnl_type="after_fees")
pnl = backtest.PNL()
print(pnl.iloc[100:105])

# Vẽ PnL
backtest.plot_PNL("VIC - MA(20/50) Strategy")
```

**Output:**

```python
           Date      time   Open   High    Low  Close    volume     ma20    ma50  position
100  2023-04-17  09:00:00  26.45  26.50  26.25  26.25  196700.0  26.4800  27.264         0
101  2023-04-17  10:00:00  26.30  26.40  26.25  26.25  246900.0  26.4700  27.201         0
102  2023-04-17  11:00:00  26.30  26.30  26.20  26.20  156200.0  26.4525  27.138         0
103  2023-04-17  13:00:00  26.25  26.40  26.25  26.30  311700.0  26.4425  27.089         0
104  2023-04-17  14:00:00  26.30  26.35  26.25  26.25  331600.0  26.4175  27.039         0

datetime
2023-04-17 09:00:00   -70.395
2023-04-17 10:00:00   -70.395
2023-04-17 11:00:00   -70.395
2023-04-17 13:00:00   -70.395
2023-04-17 14:00:00   -70.395
```

#### 4.3. Metrics - Đánh giá hiệu suất

```python
from quantvn import client
client(apikey="your-apikey-here")

from quantvn.vn.metrics import Metrics, Backtest_Derivates
from quantvn.vn.data import get_derivatives_hist

# Giả sử đã có backtest
df = get_derivatives_hist("VN30F1M", "5m")
# ... tạo position ...
df["position"] = 1  # Ví dụ đơn giản: long cả ngày

backtest = Backtest_Derivates(df, pnl_type="after_fees")
metrics = Metrics(backtest)

# Các chỉ số hiệu suất
print(f"Sharpe Ratio: {metrics.sharpe():.3f}")
print(f"Sortino Ratio: {metrics.sortino():.3f}")
print(f"Calmar Ratio: {metrics.calmar():.3f}")
print(f"Max Drawdown: {metrics.max_drawdown()*100:.2f}%")
print(f"Win Rate: {metrics.win_rate()*100:.2f}%")
print(f"Profit Factor: {metrics.profit_factor():.3f}")
print(f"Average Win: {metrics.avg_win():,.0f} VND")
print(f"Average Loss: {metrics.avg_loss():,.0f} VND")
print(f"Risk of Ruin: {metrics.risk_of_ruin():.4f}")

# Value at Risk (95% confidence)
var_95 = metrics.value_at_risk(confidence_level=0.95)
print(f"VaR (95%): {var_95:,.0f} VND")
```

**Output:**

```python
Sharpe Ratio: 0.019
Sortino Ratio: 0.024
Calmar Ratio: 0.434
Max Drawdown: -72.36%
Win Rate: 51.78%
Profit Factor: 1.003
Average Win: 11 VND
Average Loss: -12 VND
Risk of Ruin: 1.0061
VaR (95%): 25 VND
```

**Các metrics có sẵn:**

- `sharpe()`: Sharpe Ratio
- `sortino()`: Sortino Ratio
- `calmar()`: Calmar Ratio
- `max_drawdown()`: Drawdown tối đa
- `win_rate()`: Tỷ lệ thắng
- `profit_factor()`: Tỷ số lợi nhuận
- `avg_win()`: Lãi trung bình
- `avg_loss()`: Lỗ trung bình
- `avg_return()`: Return trung bình
- `volatility()`: Độ biến động
- `value_at_risk(confidence_level)`: Value at Risk
- `risk_of_ruin()`: Xác suất phá sản

---

## Ví dụ thực tế

Xem cách triển khai và chạy trực tiếp trên Google Colab:
https://colab.research.google.com/drive/1pEVYivKMNwRVxERy4mb9ujzoHrh7avJL?usp=sharing

---

## Testing

Chạy tests:

```bash
# Cài đặt dependencies cho dev
pip install -e ".[dev]"

# Chạy tests
pytest tests/

# Chạy với coverage
pytest --cov=quantvn tests/
```

---

## Đóng góp

Chúng tôi hoan nghênh mọi đóng góp! Để đóng góp:

1. Fork repository
2. Tạo branch mới (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Mở Pull Request

Vui lòng đọc [CONTRIBUTING.md](CONTRIBUTING.md) để biết thêm chi tiết.

---

## Tuyên bố miễn trách nhiệm

**QuantVN** được phát triển nhằm phục vụ mục đích nghiên cứu và học tập.

- Dữ liệu cung cấp có thể không đầy đủ hoặc không chính xác 100%
- Không khuyến nghị sử dụng cho giao dịch thực tế mà không kiểm chứng kỹ lưỡng
- Tác giả không chịu trách nhiệm về bất kỳ tổn thất tài chính nào phát sinh từ việc sử dụng thư viện này

**Lưu ý quan trọng:**

- Luôn kiểm tra và xác thực dữ liệu trước khi sử dụng
- Backtesting không đảm bảo kết quả trong tương lai
- Quản lý rủi ro là trách nhiệm của người dùng

---

## Giấy phép

Dự án này được phát hành theo giấy phép **MIT License**. Xem file [LICENSE](LICENSE) để biết thêm chi tiết.

---

## Changelog

### Version 0.1.5

- Thêm hỗ trợ cryptocurrency data từ Binance
- Cải thiện performance cho `get_stock_hist()`
- Sửa lỗi timezone cho dữ liệu phái sinh
- Thêm các metrics mới: Risk of Ruin, VaR

### Version 0.1.4

- Thêm module backtesting cho cổ phiếu
- Hỗ trợ Take Profit/Stop Loss
- Cải thiện documentation

---

## Hỗ trợ

- **GitHub Issues**: https://github.com/quantvn/quantvn-vn-markets/issues
- **Documentation**: https://quantvn.gitbook.io/quantvn-docs

---

**QuantVN** - Công cụ phân tích tài chính mạnh mẽ cho thị trường Việt Nam
