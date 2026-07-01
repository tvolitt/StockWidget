import json, time
import requests
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
        if len(trend_data) == 5:
            # 把 vols（成交量）接过来，但在小图里不画它，保持极简
            prev_close, times, prices, avgs, vols = trend_data
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
    后台静默回溯线程：采用东方财富原生分时接口，获取交易所绝对精确均价，消灭一切计算毛刺。
    """
    data_fetched = Signal(str, dict)

    def __init__(self, codes):
        super().__init__()
        self.codes = codes

    def run(self):
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        
        for code in self.codes:
            if not code: continue
            try:
                # 1. 转换代码格式以适配东方财富API (sh开头转为1.，sz/bj转为0.)
                prefix = code[:2].lower()
                ticker = code[2:]
                secid = f"1.{ticker}" if prefix == 'sh' else f"0.{ticker}"
                
                # 2. 绝密武器：调用东财原生【分时】接口（而非K线接口）
                # fields2 中: f52=现价, f56=成交量, f57=成交额, f58=精确均价！
                url = f"http://push2his.eastmoney.com/api/qt/stock/trends2/get?secid={secid}&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13&fields2=f51,f52,f53,f54,f55,f56,f57,f58&ndays=1&iscr=0&iscca=0"
                
                r = requests.get(url, headers=headers, timeout=5)
                data = r.json()
                
                # 3. 容错解析数据
                if not data or not data.get('data'):
                    continue
                    
                trends = data['data'].get('trends', [])
                if not trends:
                    continue
                    
                # 提取正确的交易日期 (如 "2023-10-27")
                first_time = trends[0].split(',')[0]
                true_date_str = first_time.split(' ')[0]
                
                p_dict = {}
                a_dict = {}
                
                for item in trends:
                    parts = item.split(',')
                    if len(parts) < 8: continue
                        
                    full_time = parts[0]
                    time_str = full_time.split(' ')[1]
                    
                    price = float(parts[2])  # 现价
                    avg = float(parts[7])    # 均价
                    vol = float(parts[5])    # 💡新增：成交量(手)
                    
                    p_dict[time_str] = price
                    a_dict[time_str] = avg
                    # 💡新增：把成交量存入字典
                    if 'v_dict' not in locals(): v_dict = {}
                    v_dict[time_str] = vol
                
                # 组装正确的数据结构传给前台
                history_data = {
                    'date': true_date_str, 
                    'p_dict': p_dict,
                    'a_dict': a_dict,
                    'v_dict': v_dict,
                    # 💡【核心修复 1】：必须为新浪接口预留出这个空字典，否则必定崩溃！
                    'cum_v_dict': {} 
                }
                
                self.data_fetched.emit(code, history_data)
                
            except Exception as e:
                print(f"后台拉取 {code} 历史分时发生错误: {e}")
            
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
        self.setFixedSize(300, 260)  # 放大版尺寸，可根据你的喜好调整
        
        self.trend_data = None
        self.fg = QColor("#FFFFFF")
        self.vwap_color = QColor("#F6AF2A")
        
    # 1. 升级 set_data，多接收 bg_color 和 opacity 两个参数
    def set_data(self, trend_data, fg_color, bg_color, opacity: float):
        self.trend_data = trend_data
        self.fg = fg_color
        
        # ==========================================
        # ↓↓↓ 核心修改：锁定纯黑 RGB，但吸取原背景的 Alpha(透明度) ↓↓↓
        # ==========================================
        self.bg = QColor(0, 0, 0)

        # self.setWindowOpacity(opacity)  # 接收主窗口的整体透明度
        self.update()

    def _calc_macd(self, prices):
        """实时推算 MACD (参数 12, 26, 9)"""
        if not prices: return [], [], []
        ema12, ema26 = [prices[0]], [prices[0]]
        
        # 1. 算 EMA
        for p in prices[1:]:
            ema12.append(ema12[-1] * 11/13 + p * 2/13)
            ema26.append(ema26[-1] * 25/27 + p * 2/27)
            
        # 2. 算 DIF
        dif = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
        
        # 3. 算 DEA 和 MACD柱
        dea = [dif[0]]
        for d in dif[1:]:
            dea.append(dea[-1] * 8/10 + d * 2/10)
            
        macd = [(d - de) * 2 for d, de in zip(dif, dea)]
        return dif, dea, macd

    def paintEvent(self, event):
        if not hasattr(self, 'trend_data') or not self.trend_data:
            return
            
        # 兼容老数据结构
        if len(self.trend_data) == 5:
            prev_close, times, prices, avgs, vols = self.trend_data
        else:
            prev_close, times, prices, avgs = self.trend_data
            vols = [0] * len(prices)

        from PySide6.QtGui import QPainter, QColor, QPen
        from PySide6.QtCore import QPointF, QRect
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        # 💡 再次拓宽到 105px，确保上下限的“价格+百分比”能完全显示
        chart_w = w - 105
        
        # 💡 三段式比例：主图 60%，成交量 20%，MACD 20%
        main_h = int(h * 0.6)
        vol_h = int(h * 0.2)
        macd_h = h - main_h - vol_h

        # 1. 锁定纯黑底色
        painter.fillRect(0, 0, w, h, getattr(self, 'bg', QColor(0, 0, 0, 230)))
        
        if not prices: return

        # 2. 算坐标比例
        max_p, min_p = max(prices), min(prices)
        y_range = max(abs(max_p - prev_close), abs(min_p - prev_close))
        y_range = y_range if y_range > 0 else prev_close * 0.01
        
        # 真实的上下限（用于右侧固定文字显示）
        p_max, p_min = prev_close + y_range, prev_close - y_range
        
        # 💡 核心修改：图表绘制上下限额外扩展 2%（0.02 * 昨收）
        # 这会把曲线向中间压缩一点，给顶部和底部的文字腾出“专属房间”
        draw_range = y_range + (prev_close * 0.02)
        draw_max = prev_close + draw_range
        draw_min = prev_close - draw_range
        
        v_max = max(vols) if vols else 1
        v_max = v_max if v_max > 0 else 1
        
        dif, dea, macd = self._calc_macd(prices)
        m_max = max(abs(max(dif + dea + macd)), abs(min(dif + dea + macd))) if dif else 0.001
        m_max = m_max if m_max != 0 else 0.001

        x_step = chart_w / 240.0
        
        # 3. 画虚线网格 (零轴)
        grid_pen = QPen(QColor(255, 255, 255, 40), 1)
        grid_pen.setStyle(Qt.DashLine)
        painter.setPen(grid_pen)
        # 主图零轴
        main_mid_y = main_h / 2
        painter.drawLine(0, main_mid_y, chart_w, main_mid_y)
        # MACD 零轴
        macd_mid_y = main_h + vol_h + macd_h / 2
        painter.drawLine(0, macd_mid_y, chart_w, macd_mid_y)

        # 4. 开始画线和柱子
        pts_p, pts_a = [], []
        for i, (p, a, v, d, de, m) in enumerate(zip(prices, avgs, vols, dif, dea, macd)):
            x = i * x_step
            
            # 💡 核心修改：使用扩展后的 draw_max 和 draw_min 进行映射
            y_p = main_h - (p - draw_min) / (draw_max - draw_min) * main_h
            y_a = main_h - (a - draw_min) / (draw_max - draw_min) * main_h
            pts_p.append(QPointF(x, y_p))
            pts_a.append(QPointF(x, y_a))
            
            # 画成交量柱 (红绿配)
            y_v = main_h + vol_h - (v / v_max) * vol_h
            v_color = QColor(255, 50, 50, 200) if i == 0 or p >= prices[i-1] else QColor(50, 255, 50, 200)
            painter.setPen(QPen(v_color, 1))
            painter.fillRect(QRect(x, y_v, max(1, x_step-1), main_h + vol_h - y_v), v_color)
            
            # 画 MACD 柱 (红绿配)
            y_m = macd_mid_y - (m / m_max) * (macd_h / 2)
            m_color = QColor(255, 50, 50, 200) if m >= 0 else QColor(50, 255, 50, 200)
            if m >= 0:
                painter.fillRect(QRect(x, y_m, max(1, x_step-1), macd_mid_y - y_m), m_color)
            else:
                painter.fillRect(QRect(x, macd_mid_y, max(1, x_step-1), y_m - macd_mid_y), m_color)

        # 5. 连线 (价格白线，均价黄线)
        painter.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
        painter.drawPolyline(pts_p)
        painter.setPen(QPen(QColor(255, 255, 0, 180), 1.5))
        painter.drawPolyline(pts_a)

        # 6. 连线 (DIF 白线，DEA 蓝线)
        pts_dif = [QPointF(i * x_step, macd_mid_y - (d / m_max) * (macd_h / 2)) for i, d in enumerate(dif)]
        pts_dea = [QPointF(i * x_step, macd_mid_y - (de / m_max) * (macd_h / 2)) for i, de in enumerate(dea)]
        painter.setPen(QPen(QColor(255, 255, 255, 150), 1))
        painter.drawPolyline(pts_dif)
        painter.setPen(QPen(QColor(50, 200, 255, 150), 1))
        painter.drawPolyline(pts_dea)

        # ==========================================
        # 7. 绘制右侧数值体系（带物理隔离与透明底，靠左对齐）
        # ==========================================
        def draw_dynamic_tag(y_pos, text, color):
            """专门给现价、均价用的游标：被限制在图表内部，绝不越界打扰上下限"""
            y_pos = max(20, min(main_h - 20, y_pos))
            
            # 💡 chart_w + 5: 避免文字死死贴在线上，留 5px 呼吸空间
            # 宽度 90 足够容纳下百元股的超长文本
            rect = QRect(chart_w + 5, int(y_pos - 10), 90, 20)
            painter.setPen(color)
            # 💡 改为靠左对齐 (Qt.AlignLeft)
            painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, text)

        # 7.1 画真实的上下限及零线 (价格 + 百分比)
        pct_max = (p_max / prev_close - 1) * 100
        pct_min = (p_min / prev_close - 1) * 100
        zero_y = main_h / 2 
        
        # 💡 宽度给到 100，格式全部统一为： 价格(百分比)
        painter.setPen(QColor(255, 50, 50))
        painter.drawText(QRect(chart_w + 5, 0, 100, 20), Qt.AlignLeft | Qt.AlignVCenter, f"{p_max:.2f}({pct_max:+.2f}%)")
        
        painter.setPen(QColor(50, 255, 50))
        painter.drawText(QRect(chart_w + 5, main_h - 20, 100, 20), Qt.AlignLeft | Qt.AlignVCenter, f"{p_min:.2f}({pct_min:+.2f}%)")
        
        painter.setPen(QColor(150, 150, 150))
        painter.drawText(QRect(chart_w + 5, int(zero_y - 10), 100, 20), Qt.AlignLeft | Qt.AlignVCenter, f"{prev_close:.2f}(0.00%)")

        # 7.2 画最新均价 (黄色，价格 + 百分比)
        last_a = avgs[-1]
        last_a_y = main_h - (last_a - draw_min) / (draw_max - draw_min) * main_h
        
        # 💡 新增：计算均价相对于昨收的涨跌幅
        pct_a = (last_a / prev_close - 1) * 100 
        
        # 💡 格式化为与上下限完全一样的：价格(百分比)
        draw_dynamic_tag(last_a_y, f"{last_a:.2f}({pct_a:+.2f}%)", QColor(255, 255, 0))

        # 7.3 画最新现价 (价格+百分比)
        last_p = prices[-1]
        last_p_y = main_h - (last_p - draw_min) / (draw_max - draw_min) * main_h
        pct_p = (last_p / prev_close - 1) * 100
        
        if pct_p > 0.01: tag_color = QColor(255, 50, 50)
        elif pct_p < -0.01: tag_color = QColor(50, 255, 50)
        else: tag_color = QColor(200, 200, 200)
            
        draw_dynamic_tag(last_p_y, f"{last_p:.2f}({pct_p:+.2f}%)", tag_color)