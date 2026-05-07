import json, time
from PySide6.QtCore import QThread, Signal
from PySide6.QtCore import Qt, QRect, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import QStyledItemDelegate, QWidget
from PySide6.QtGui import QPainterPath

# ----- 颜色配置 -----
UP_COLOR = QColor("#dd2100")
DOWN_COLOR = QColor("#019933")
NEUTRAL_COLOR = QColor("#494949")

class SimpleTableModel(QAbstractTableModel):
    """
    主浮窗表格数据与格式
    """
    def __init__(self, rows=None, headers=None, align_right_cols=None, parent=None):
        super().__init__(parent)
        self._rows = rows or []
        self._headers = headers or []
        self._align_right = align_right_cols or []
        self.default_color = False
        self.fg_color = QColor("#FFFFFF")
        self._row_meta = []

    def set_color_scheme(self, default: bool, fg: QColor):
        self.default_color = bool(default)
        self.fg_color = QColor(fg)

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)
    
    def columnCount(self, parent=QModelIndex()):
        return len(self._rows[0]) if self._rows else len(self._headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        cell = "" if c >= len(self._rows[r]) else self._rows[r][c]

        if role == Qt.UserRole:
            if isinstance(cell, dict):
                # 如果是K线，返回K线需要的元组
                if "k" in cell:
                    return cell["k"]
                # 如果是分时线，直接返回整个字典
                if "trend" in cell:
                    return cell
            return None

        if role == Qt.DisplayRole:
            return "" if isinstance(cell, dict) else str(cell)

        if role == Qt.TextAlignmentRole:
            return (Qt.AlignRight | Qt.AlignVCenter) if c in self._align_right else (Qt.AlignLeft | Qt.AlignVCenter)

        if role == Qt.ForegroundRole:
            if not self.default_color:
                return self.fg_color

            meta = self._row_meta[r] if 0 <= r < len(self._row_meta) else {}
            header = self._headers[c] if 0 <= c < len(self._headers) else ""
            sign = 0
            if header in ("涨跌值", "涨跌幅", "现价"):
                sign = int(meta.get("delta", 0))
            elif header == "委比":
                sign = int(meta.get("commi", 0))
            elif header == "均价":
                sign = int(meta.get("avg", 0))
            elif header == "买一":
                sign = int(meta.get("b1", 0))
            elif header == "卖一":
                sign = int(meta.get("s1", 0))
            else:
                return self.fg_color

            if sign > 0:
                return UP_COLOR
            if sign < 0:
                return DOWN_COLOR
            return NEUTRAL_COLOR

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal and 0 <= section < len(self._headers):
            return self._headers[section]
        return None

    def set_rows_headers(self, rows, headers, meta=None):
        self.beginResetModel()
        self._rows = rows or []
        self._headers = headers or []
        self._row_meta = list(meta or [{} for _ in self._rows])
        self.endResetModel()

    def set_align_right_cols(self, cols_idx):
        self._align_right = set(cols_idx or [])


class KLineDelegate(QStyledItemDelegate):
    """
    当日K线图，基于昨收，今开，最高，最低，实时价
    """
    def __init__(self, parent=None, base_pt=12):
        super().__init__(parent)
        self.default_color = False
        self.fg = QColor("#FFFFFF")
        self.base_pt = max(1, int(base_pt))
        self.scale = 1.0  # 缩放

    def update_scheme(self, default_color: bool, fg: QColor):
        self.default_color = bool(default_color)
        self.fg = QColor(fg)

    def set_point_size(self, pt: int):
        self.scale = max(0.5, min(1.5, float(pt) / float(self.base_pt)))

    def paint(self, painter: QPainter, option, index):
        k = index.data(Qt.UserRole)
        if not k or not isinstance(k, tuple) or len(k) != 5:
            super().paint(painter, option, index)
            return

        o, c, h, l, p = k
        if h < l: h, l = l, h

        cell = option.rect
        rect = cell.adjusted(2, 2, -2, -2)

        sc = max(0.5, min(1.5, self.scale))
        vpad = max(2, int(rect.height() * (0.12 + 0.06 * (sc - 1))))   # ~12%~18%
        h_eff = max(2, rect.height() - 2 * vpad)
        krect = QRect(rect.left(), rect.top() + vpad, rect.width(), h_eff)

        def y_for(v):
            if h == l == p:
                y = 0.5
            else:
                y = (v - min(l,p)) / (max(h,p) - min(l,p))
            return krect.top() + (1 - y) * krect.height()

        y_o, y_c, y_h, y_l, y_p = (y_for(o), y_for(c), y_for(h), y_for(l), y_for(p))

        painter.save()
        painter.setClipRect(cell)
        painter.setRenderHint(QPainter.Antialiasing, True)

        body_w = max(5, min(int(krect.width() * 0.4 * sc), 10))
        x = krect.center().x()

        # 昨收虚线
        dash_col = QColor(NEUTRAL_COLOR if self.default_color else self.fg)
        dash_col.setAlpha(180)
        painter.setPen(QPen(dash_col, 1, Qt.DashLine))
        painter.drawLine(x - body_w, y_p, x + body_w, y_p)

        kcolor = self.fg
        if self.default_color:
            if c>o:
                kcolor = UP_COLOR
            elif c<o:
                kcolor = DOWN_COLOR
            else:
                kcolor = NEUTRAL_COLOR

        top, bot = min(y_o, y_c), max(y_o, y_c)
        body_h = max(2, bot - top)
        body_x = x - body_w // 2

        painter.setPen(QPen(kcolor, 1))
        if c != o:
            # 实体
            painter.drawRect(body_x, top, body_w, body_h)
        else:
            # 一字实体
            painter.drawLine(body_x, y_c, body_x+body_w, y_c)
        if y_h < top:
            # 上影线
            painter.drawLine(x, y_h, x, top)
        if y_l > bot:
            # 下影线
            painter.drawLine(x, bot, x, y_l)
        if c < o: 
            # 填充实体（空阳线）
            painter.fillRect(body_x, top, body_w, body_h, QBrush(kcolor))

        painter.restore()

class TrendDelegate(QStyledItemDelegate):
    """
    分时线图（含均价线），采用本地数据打点
    """
    def __init__(self, parent=None, base_pt=12):
        super().__init__(parent)
        self.default_color = False
        self.fg = QColor("#FFFFFF")
        self.vwap_color = QColor("#F6D32A")  # 经典的分时均价黄线
        self.scale = 1.0
        self.base_pt = max(1, int(base_pt))

    def update_scheme(self, default_color: bool, fg: QColor):
        self.default_color = bool(default_color)
        self.fg = QColor(fg)

    # ==========================================
    # ↓↓↓ 把下面这个缺失的方法粘贴到这里 ↓↓↓
    # ==========================================
    def set_point_size(self, pt: int):
        """根据当前的字体大小，动态计算画笔的缩放比例"""
        self.scale = max(0.5, min(1.5, float(pt) / float(self.base_pt)))
    # ==========================================

    def paint(self, painter: QPainter, option, index):
        data = index.data(Qt.UserRole)
        # 验证数据结构
        if not data or not isinstance(data, dict) or "trend" not in data:
            super().paint(painter, option, index)
            return

        trend_data = data["trend"]
        # 兼容保护：提取时间戳
        if len(trend_data) == 4:
            prev_close, times, prices, avgs = trend_data
        else:
            return  # 如果数据还没刷新过来，直接跳过

        if not prices:
            return

        cell = option.rect
        rect = cell.adjusted(2, 2, -2, -2)

        painter.save()
        painter.setClipRect(cell)
        painter.setRenderHint(QPainter.Antialiasing, True)

        max_p = max(max(prices), max(avgs)) if avgs else max(prices)
        min_p = min(min(prices), min(avgs)) if avgs else min(prices)
        max_diff = max(abs(max_p - prev_close), abs(min_p - prev_close))
        max_diff = max_diff * 1.05 if max_diff > 0 else prev_close * 0.01

        y_max = prev_close + max_diff
        y_min = prev_close - max_diff

        def get_y(val):
            ratio = (val - y_min) / (y_max - y_min) if y_max > y_min else 0.5
            return rect.bottom() - ratio * rect.height()

        # 【核心黑科技：A股 240 分钟绝对坐标转换器】
        def get_x(idx):
            if times and idx < len(times):
                t_str = times[idx]
                try:
                    h, m = map(int, t_str.split(':'))
                    if h < 9 or (h == 9 and m < 30):
                        m_idx = 0                  # 集合竞价和盘前
                    elif h < 11 or (h == 11 and m <= 30):
                        m_idx = (h - 9) * 60 + m - 30  # 上午盘
                    elif h >= 13:
                        m_idx = 120 + (h - 13) * 60 + m # 下午盘
                    else:
                        m_idx = 120                # 午休期间
                except:
                    m_idx = 0
            else:
                m_idx = idx

            # 强行把 X 轴锁定在 240 等份，绝不拉伸！
            m_idx = max(0, min(240, m_idx))
            return rect.left() + (m_idx / 240.0) * rect.width()

        # 画昨收基准虚线 (0% 轴)
        y_prev = get_y(prev_close)
        dash_col = QColor(NEUTRAL_COLOR if self.default_color else self.fg)
        dash_col.setAlpha(100)
        painter.setPen(QPen(dash_col, 1, Qt.DashLine))
        painter.drawLine(rect.left(), int(y_prev), rect.right(), int(y_prev))

        total_pts = len(prices)
        if total_pts == 0:
            painter.restore()
            return

        # 刚开盘时的单点处理
        if total_pts == 1:
            px = get_x(0)
            py = get_y(prices[0])
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.fg)
            painter.drawEllipse(int(px) - 2, int(py) - 2, 4, 4)
            painter.restore()
            return

        # 画均价线（黄线）
        if avgs and len(avgs) == total_pts:
            path_avg = QPainterPath()
            path_avg.moveTo(get_x(0), get_y(avgs[0]))
            for i in range(1, total_pts):
                path_avg.lineTo(get_x(i), get_y(avgs[i]))

            painter.setPen(QPen(self.vwap_color, max(1, int(1.2 * self.scale))))
            painter.drawPath(path_avg)

        # 画分时价格线
        line_color = self.fg
        if self.default_color:
            current = prices[-1]
            if current > prev_close: line_color = UP_COLOR
            elif current < prev_close: line_color = DOWN_COLOR
            else: line_color = NEUTRAL_COLOR

        path_price = QPainterPath()
        path_price.moveTo(get_x(0), get_y(prices[0]))
        for i in range(1, total_pts):
            path_price.lineTo(get_x(i), get_y(prices[i]))

        painter.setPen(QPen(line_color, max(1, int(1.5 * self.scale))))
        painter.drawPath(path_price)

        painter.restore()

class TrendBackfillThread(QThread):
    """
    后台静默回溯线程：负责在软件启动时，按部就班地拉取当天的历史分时数据。
    绝对安全策略：每拉取一只股票，强制休眠 0.5 秒，伪装成人类点击，绝不触发反爬封号。
    """
    # 定义信号：拉取成功一只，就向主线程汇报一只 (股票代码, 历史数据字典)
    data_fetched = Signal(str, dict)

    def __init__(self, codes):
        super().__init__()
        self.codes = codes

    def run(self):
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        
        for code in self.codes:
            if not code: continue
            try:
                # 腾讯 m1 接口
                url = f"https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={code},m1,,240"
                import requests
                r = requests.get(url, headers=headers, timeout=5)
                data = r.json()
                
                m1_data = data.get('data', {}).get(code, {}).get('m1', [])
                if not m1_data:
                    continue
                
                # 【核心修复 1】精准提取“真实的最新交易日” (如 "20231027")
                latest_date_raw = m1_data[-1][0][:8]
                # 转换成与新浪快照完美匹配的格式 "2023-10-27"，防止周末被意外清空
                true_date_str = f"{latest_date_raw[:4]}-{latest_date_raw[4:6]}-{latest_date_raw[6:]}"
                
                p_dict = {}
                a_dict = {}
                cum_vol = 0.0
                cum_amt = 0.0
                
                for item in m1_data:
                    # 【核心修复 2】时间轴净化：无情过滤掉所有非今天(昨天/前天)的 240 根残留 K 线
                    if not item[0].startswith(latest_date_raw):
                        continue
                        
                    time_raw = item[0][-4:]
                    time_str = f"{time_raw[:2]}:{time_raw[2:]}"
                    
                    # 【核心修复 3】索引 2 才是该分钟的真实收盘价 (之前误用了 4 最低价)
                    price = float(item[2])
                    vol = float(item[5])
                    
                    # 均价计算保持不变
                    cum_vol += vol
                    cum_amt += price * vol 
                    avg = cum_amt / cum_vol if cum_vol > 0 else price
                    
                    p_dict[time_str] = price
                    a_dict[time_str] = avg
                
                # 组装正确的数据结构传给前台
                history_data = {
                    'date': true_date_str, 
                    'p_dict': p_dict,
                    'a_dict': a_dict
                }
                
                self.data_fetched.emit(code, history_data)
                
            except Exception as e:
                pass
            
            # 护身符：慢慢拉取，绝不封号
            time.sleep(0.5)

class TrendMagnifierWindow(QWidget):
    """
    分时图悬浮放大镜窗口
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # 设置为不受主窗口限制的提示级悬浮窗
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(280, 180)  # 放大版尺寸，可根据你的喜好调整
        
        self.trend_data = None
        self.fg = QColor("#FFFFFF")
        self.vwap_color = QColor("#F6D32A")
        
    # 1. 升级 set_data，多接收 bg_color 和 opacity 两个参数
    def set_data(self, trend_data, fg_color, bg_color, opacity: float):
        self.trend_data = trend_data
        self.fg = fg_color
        self.bg = bg_color  # 接收主窗口的背景色（自带透明度 alpha）
        self.setWindowOpacity(opacity)  # 接收主窗口的整体透明度
        self.update()

    def paintEvent(self, event):
        if not self.trend_data or len(self.trend_data) < 3:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        
        rect = self.rect()
        
        # ==========================================
        # ↓↓↓ 修改背景渲染：完全沿用主窗口配置 ↓↓↓
        # ==========================================
        # 使用主窗口同步过来的背景色（包含 rgba）
        painter.fillRect(rect, self.bg)
        
        # 让边框线也融入整体风格，取前景色 fg，并给一个 80 的透明度（和主界面的网格线逻辑一样）
        border_color = QColor(self.fg.red(), self.fg.green(), self.fg.blue(), 80)
        painter.setPen(QPen(border_color, 1))
        painter.drawRect(0, 0, rect.width()-1, rect.height()-1)
        # ==========================================

        # 留出内边距
        pad = 10
        chart_rect = rect.adjusted(pad, pad, -pad, -pad)

        # 容错解析数据
        if len(self.trend_data) == 4:
            prev_close, times, prices, avgs = self.trend_data
        else:
            prev_close, prices, avgs = self.trend_data
            times = []

        if not prices:
            return

        max_p = max(max(prices), max(avgs)) if avgs else max(prices)
        min_p = min(min(prices), min(avgs)) if avgs else min(prices)
        max_diff = max(abs(max_p - prev_close), abs(min_p - prev_close))
        max_diff = max_diff * 1.05 if max_diff > 0 else prev_close * 0.01

        y_max = prev_close + max_diff
        y_min = prev_close - max_diff

        def get_y(val):
            ratio = (val - y_min) / (y_max - y_min) if y_max > y_min else 0.5
            return chart_rect.bottom() - ratio * chart_rect.height()

        def get_x(idx):
            if times and idx < len(times):
                t_str = times[idx]
                try:
                    h, m = map(int, t_str.split(':'))
                    if h < 9 or (h == 9 and m < 30): m_idx = 0
                    elif h < 11 or (h == 11 and m <= 30): m_idx = (h - 9) * 60 + m - 30
                    elif h >= 13: m_idx = 120 + (h - 13) * 60 + m
                    else: m_idx = 120
                except:
                    m_idx = 0
            else:
                m_idx = idx

            m_idx = max(0, min(240, m_idx))
            return chart_rect.left() + (m_idx / 240.0) * chart_rect.width()

        # 画昨收虚线
        y_prev = get_y(prev_close)
        painter.setPen(QPen(QColor(0, 0, 0), 1, Qt.DashLine))
        painter.drawLine(chart_rect.left(), int(y_prev), chart_rect.right(), int(y_prev))

        total_pts = len(prices)
        if total_pts == 0: return

        # 画均价线 (黄)
        if avgs and len(avgs) == total_pts:
            path_avg = QPainterPath()
            path_avg.moveTo(get_x(0), get_y(avgs[0]))
            for i in range(1, total_pts):
                path_avg.lineTo(get_x(i), get_y(avgs[i]))
            painter.setPen(QPen(self.vwap_color, 2)) # 放大版画笔调粗为 2
            painter.drawPath(path_avg)

        # 画价格线 (白/红/绿)
        line_color = self.fg
        current = prices[-1]
        # 在这里直接引入你之前定义的宏或直接写死颜色
        if current > prev_close: line_color = QColor("#dd2100") 
        elif current < prev_close: line_color = QColor("#019933")

        path_price = QPainterPath()
        path_price.moveTo(get_x(0), get_y(prices[0]))
        for i in range(1, total_pts):
            path_price.lineTo(get_x(i), get_y(prices[i]))

        painter.setPen(QPen(line_color, 2)) # 放大版画笔调粗为 2
        painter.drawPath(path_price)