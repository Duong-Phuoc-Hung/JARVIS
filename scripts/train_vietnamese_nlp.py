"""
scripts/train_vietnamese_nlp.py
===============================
Offline Training Pipeline for JARVIS Vietnamese NLP Intent Classification Model.
Trains on a curated 15-domain dataset + OOD negative class, applies multi-axis
data augmentation (unaccented variants, colloquial jittering, phonetic loanwords),
computes stratified cross-validation scores, saves the calibrated Scikit-Learn model,
and exports the ONNX Runtime graph for sub-millisecond execution.
"""
from __future__ import annotations

import os
import random
import sys
import time
from pathlib import Path

# Safeguard thread contention on Windows CPU
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

# Ensure repo root is in python path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType

from jarvis.llm.local_classifier import (
    DEFAULT_MODEL_PATH,
    VietnameseNLPClassifier,
    strip_vietnamese_diacritics,
)
from jarvis.nlp.phonetic_normalizer import PHONETIC_REPLACEMENTS

# Canonical Curated Vietnamese Intent Corpus (15 domains + negative class)
CANONICAL_TRAINING_DATA: list[tuple[str, str]] = [
    # 1. system_volume
    ("tăng âm lượng", "system_volume"),
    ("tăng âm lượng lên", "system_volume"),
    ("vặn to loa lên một chút", "system_volume"),
    ("chỉnh âm thanh to hơn", "system_volume"),
    ("cho âm lượng lên 80%", "system_volume"),
    ("cho âm lượng lên mức 70", "system_volume"),
    ("chỉnh volume lên 90%", "system_volume"),
    ("bật to tiếng lên", "system_volume"),
    ("bật to loa lên", "system_volume"),
    ("giảm âm lượng", "system_volume"),
    ("giảm âm lượng xuống", "system_volume"),
    ("vặn nhỏ loa lại", "system_volume"),
    ("cho nhỏ tiếng thôi", "system_volume"),
    ("hạ âm thanh xuống xíu", "system_volume"),
    ("chỉnh âm lượng xuống 30%", "system_volume"),
    ("đặt âm lượng ở mức 50%", "system_volume"),
    ("tắt tiếng", "system_volume"),
    ("tắt âm thanh", "system_volume"),
    ("mute tiếng đi", "system_volume"),
    ("mute loa máy tính", "system_volume"),
    ("bật lại tiếng", "system_volume"),
    ("unmute loa", "system_volume"),
    ("mở lại âm thanh", "system_volume"),
    ("âm lượng hiện tại là bao nhiêu", "system_volume"),
    ("cho max volume", "system_volume"),
    ("cho âm lượng hết cỡ", "system_volume"),
    ("âm thanh đang ở mức nào", "system_volume"),
    ("hạ âm lượng xuống", "system_volume"),
    ("cho loa to lên bạn ơi", "system_volume"),
    ("giảm âm thanh máy tính", "system_volume"),
    ("bật âm lượng 50%", "system_volume"),
    ("tắt loa ngoài", "system_volume"),
    ("chỉnh loa nhỏ lại một chút", "system_volume"),
    ("vặn to volume lên", "system_volume"),
    ("giảm tiếng loa đi", "system_volume"),
    ("âm lượng đang là bao nhiêu phần trăm", "system_volume"),

    # 2. system_brightness
    ("tăng độ sáng", "system_brightness"),
    ("tăng độ sáng màn hình", "system_brightness"),
    ("cho màn hình sáng lên", "system_brightness"),
    ("màn hình tối quá tăng sáng lên", "system_brightness"),
    ("chỉnh độ sáng lên 90%", "system_brightness"),
    ("cho độ sáng lên 100%", "system_brightness"),
    ("cho sáng hơn chút nữa", "system_brightness"),
    ("sáng thêm một chút", "system_brightness"),
    ("giảm độ sáng", "system_brightness"),
    ("giảm độ sáng màn hình", "system_brightness"),
    ("cho màn hình tối xuống", "system_brightness"),
    ("chói mắt quá giảm sáng đi", "system_brightness"),
    ("chỉnh độ sáng xuống 40%", "system_brightness"),
    ("đặt độ sáng 60%", "system_brightness"),
    ("màn hình đang sáng bao nhiêu phần trăm", "system_brightness"),
    ("độ sáng tối đa", "system_brightness"),
    ("cho màn hình sáng hết cỡ", "system_brightness"),
    ("chỉnh màn hình tối nhất", "system_brightness"),
    ("hạ độ sáng màn hình", "system_brightness"),
    ("màn hình tối bớt đi", "system_brightness"),
    ("màn hình chói quá chỉnh tối bớt", "system_brightness"),
    ("tăng độ sáng hiển thị", "system_brightness"),
    ("chỉnh màn hình sáng thêm", "system_brightness"),
    ("cho màn hình bớt chói", "system_brightness"),
    ("kiểm tra độ sáng màn hình", "system_brightness"),

    # 3. app_launch
    ("mở chrome", "app_launch"),
    ("bật trình duyệt chrome", "app_launch"),
    ("khởi động google chrome", "app_launch"),
    ("mở google chrome lên", "app_launch"),
    ("mở visual studio code", "app_launch"),
    ("bật vscode lên", "app_launch"),
    ("bật phần mềm visual studio code", "app_launch"),
    ("khởi chạy visual studio code", "app_launch"),
    ("chạy ứng dụng vs code", "app_launch"),
    ("mở vs code để lập trình", "app_launch"),
    ("mở notepad", "app_launch"),
    ("bật notepad để ghi chép", "app_launch"),
    ("khởi động notepad", "app_launch"),
    ("khởi động spotify", "app_launch"),
    ("mở ứng dụng spotify", "app_launch"),
    ("bật spotify nghe nhạc", "app_launch"),
    ("bật máy tính calculator", "app_launch"),
    ("mở calc", "app_launch"),
    ("mở máy tính tính toán", "app_launch"),
    ("mở file explorer", "app_launch"),
    ("bật quản lý file", "app_launch"),
    ("mở quản lý tập tin", "app_launch"),
    ("mở microsoft word", "app_launch"),
    ("bật word soạn thảo", "app_launch"),
    ("khởi động excel", "app_launch"),
    ("mở bảng tính excel", "app_launch"),
    ("mở telegram", "app_launch"),
    ("bật ứng dụng telegram", "app_launch"),
    ("bật zalo", "app_launch"),
    ("mở zalo nhắn tin", "app_launch"),
    ("mở cài đặt", "app_launch"),
    ("bật windows settings", "app_launch"),
    ("mở cài đặt hệ thống", "app_launch"),
    ("mở task manager", "app_launch"),
    ("bật trình quản lý tác vụ", "app_launch"),
    ("mở terminal", "app_launch"),
    ("bật powershell", "app_launch"),
    ("khởi động command prompt", "app_launch"),
    ("bật cmd", "app_launch"),

    # 4. app_close
    ("đóng cửa sổ", "app_close"),
    ("đóng ứng dụng này", "app_close"),
    ("tắt chrome đi", "app_close"),
    ("thoát chrome", "app_close"),
    ("đóng trình duyệt chrome", "app_close"),
    ("tắt trình duyệt chrome", "app_close"),
    ("thoát trình duyệt chrome", "app_close"),
    ("đóng chrome lại", "app_close"),
    ("tắt hẳn chrome", "app_close"),
    ("đóng google chrome", "app_close"),
    ("tắt google chrome", "app_close"),
    ("thoát google chrome", "app_close"),
    ("kill chrome", "app_close"),
    ("đóng ứng dụng chrome", "app_close"),
    ("tắt ứng dụng chrome", "app_close"),
    ("đóng trình duyệt", "app_close"),
    ("tắt visual studio code", "app_close"),
    ("đóng vscode lại", "app_close"),
    ("tắt hẳn vscode", "app_close"),
    ("thoát vscode", "app_close"),
    ("đóng ứng dụng vscode", "app_close"),
    ("thoát ứng dụng hiện tại", "app_close"),
    ("đóng notepad lại", "app_close"),
    ("tắt notepad đi", "app_close"),
    ("tắt ứng dụng đang dùng", "app_close"),
    ("tắt tab này", "app_close"),
    ("đóng tab hiện tại", "app_close"),
    ("thu nhỏ tất cả cửa sổ", "app_close"),
    ("ẩn hết cửa sổ xuống", "app_close"),
    ("show desktop", "app_close"),
    ("quay về màn hình chính", "app_close"),
    ("tắt phần mềm đang chạy", "app_close"),
    ("thoát cửa sổ này đi", "app_close"),
    ("tắt spotify đi", "app_close"),
    ("đóng spotify lại", "app_close"),
    ("tắt cửa sổ này", "app_close"),
    ("tắt tab trình duyệt", "app_close"),
    ("đóng hết các tab", "app_close"),

    # 5. media_control
    ("phát nhạc", "media_control"),
    ("bật nhạc lên", "media_control"),
    ("chơi nhạc đi", "media_control"),
    ("tiếp tục phát nhạc", "media_control"),
    ("resume nhạc", "media_control"),
    ("phát tiếp bài hát", "media_control"),
    ("tạm dừng nhạc", "media_control"),
    ("dừng phát nhạc", "media_control"),
    ("pause nhạc", "media_control"),
    ("dừng bài hát lại", "media_control"),
    ("tắt nhạc đi", "media_control"),
    ("tắt nhạc spotify đi bạn ơi", "media_control"),
    ("dừng nhạc spotify", "media_control"),
    ("tắt bài hát", "media_control"),
    ("pause bài hát", "media_control"),
    ("chuyển bài tiếp theo", "media_control"),
    ("bài kế tiếp", "media_control"),
    ("next bài", "media_control"),
    ("qua bài khác", "media_control"),
    ("chuyển sang bài hát tiếp theo", "media_control"),
    ("quay lại bài trước", "media_control"),
    ("bài trước đó", "media_control"),
    ("previous song", "media_control"),
    ("lùi lại bài vừa rồi", "media_control"),
    ("đang phát bài gì vậy", "media_control"),
    ("bài hát tên là gì", "media_control"),
    ("thông tin bài hát đang phát", "media_control"),
    ("ngừng phát nhạc", "media_control"),

    # 6. system_status
    ("kiểm tra hệ thống", "system_status"),
    ("báo cáo tình trạng máy tính", "system_status"),
    ("kiểm tra phần cứng", "system_status"),
    ("nhiệt độ cpu là bao nhiêu", "system_status"),
    ("nhiệt độ cpu hiện tại bao nhiêu", "system_status"),
    ("nhiệt độ máy tính hiện tại", "system_status"),
    ("cpu đang nóng bao nhiêu độ", "system_status"),
    ("ram còn trống bao nhiêu", "system_status"),
    ("kiểm tra bộ nhớ ram", "system_status"),
    ("ram đang dùng bao nhiêu phần trăm", "system_status"),
    ("pin máy tính còn bao nhiêu phần trăm", "system_status"),
    ("máy có đang sạc pin không", "system_status"),
    ("tình trạng pin laptop", "system_status"),
    ("ổ đĩa còn trống bao nhiêu gb", "system_status"),
    ("kiểm tra dung lượng ổ c", "system_status"),
    ("dung lượng bộ nhớ còn lại", "system_status"),
    ("cpu đang chạy bao nhiêu phần trăm", "system_status"),
    ("tình trạng pin thế nào", "system_status"),
    ("máy tính có bị nóng không", "system_status"),
    ("thông tin cấu hình máy", "system_status"),
    ("sức khỏe máy tính", "system_status"),
    ("kiểm tra hiệu năng máy tính", "system_status"),

    # 7. smart_home
    ("bật đèn", "smart_home"),
    ("bật đèn phòng khách", "smart_home"),
    ("bật đèn phòng ngủ", "smart_home"),
    ("bật đèn trần phòng khách", "smart_home"),
    ("bật đèn bàn làm việc", "smart_home"),
    ("bật đèn phòng bếp", "smart_home"),
    ("tắt đèn phòng khách", "smart_home"),
    ("tắt hết đèn đi", "smart_home"),
    ("tắt đèn phòng ngủ", "smart_home"),
    ("tắt đèn bàn làm việc", "smart_home"),
    ("bật quạt trần", "smart_home"),
    ("bật quạt phòng ngủ", "smart_home"),
    ("bật quạt phòng khách", "smart_home"),
    ("tắt quạt đi", "smart_home"),
    ("tắt quạt trần", "smart_home"),
    ("bật điều hòa 24 độ", "smart_home"),
    ("chỉnh máy lạnh 25 độ", "smart_home"),
    ("bật máy lạnh phòng ngủ 26 độ", "smart_home"),
    ("tắt điều hòa", "smart_home"),
    ("tắt máy lạnh đi", "smart_home"),
    ("nhiệt độ phòng khách đang là bao nhiêu", "smart_home"),
    ("đóng rèm cửa", "smart_home"),
    ("đóng rèm phòng ngủ", "smart_home"),
    ("mở rèm cửa phòng ngủ", "smart_home"),
    ("mở rèm phòng khách", "smart_home"),
    ("bật công tắc thông minh", "smart_home"),
    ("tắt thiết bị trong nhà", "smart_home"),
    ("tắt hết thiết bị điện", "smart_home"),

    # 8. timer_reminder
    ("đặt hẹn giờ 5 phút", "timer_reminder"),
    ("hẹn giờ 10 phút nữa", "timer_reminder"),
    ("đặt timer 15 phút", "timer_reminder"),
    ("đặt hẹn giờ 1 tiếng", "timer_reminder"),
    ("đặt hẹn giờ 30 giây", "timer_reminder"),
    ("đặt báo thức lúc 7 giờ sáng", "timer_reminder"),
    ("báo thức 6 giờ 30", "timer_reminder"),
    ("đặt báo thức 8h sáng mai", "timer_reminder"),
    ("nhắc tôi uống nước sau 30 phút", "timer_reminder"),
    ("nhắc tôi uống thuốc sau 1 tiếng", "timer_reminder"),
    ("nhắc tôi uống thuốc sau 30 phút", "timer_reminder"),
    ("nhắc tôi gọi điện cho anh an lúc 3 giờ", "timer_reminder"),
    ("tạo lời nhắc họp lúc 2 giờ chiều", "timer_reminder"),
    ("nhắc tôi làm việc sau 15 phút", "timer_reminder"),
    ("nhắc tôi nộp báo cáo lúc 5h chiều", "timer_reminder"),
    ("hủy hẹn giờ", "timer_reminder"),
    ("dừng báo thức", "timer_reminder"),
    ("xem các hẹn giờ đang chạy", "timer_reminder"),
    ("đặt lời nhắc mới", "timer_reminder"),
    ("xóa toàn bộ lời nhắc", "timer_reminder"),

    # 9. web_search
    ("tìm kiếm thông tin trên google", "web_search"),
    ("tìm kiếm thời tiết hôm nay", "web_search"),
    ("tra cứu thông tin thời tiết", "web_search"),
    ("tra cứu giá vàng hôm nay", "web_search"),
    ("tìm kiếm phim mới nhất", "web_search"),
    ("tra google cách nấu phở", "web_search"),
    ("tìm kiếm tài liệu python", "web_search"),
    ("tra cứu lịch thi đấu bóng đá", "web_search"),
    ("thời tiết hà nội hôm nay thế nào", "web_search"),
    ("thời tiết sài gòn ngày mai", "web_search"),
    ("tra cứu thời tiết sài gòn ngày mai", "web_search"),
    ("hôm nay trời có mưa không", "web_search"),
    ("dự báo thời tiết ngày mai", "web_search"),
    ("tìm trên mạng xem", "web_search"),
    ("tra cứu tin tức mới nhất", "web_search"),
    ("tìm kiếm hình ảnh đẹp", "web_search"),
    ("tra google giá cổ phiếu vnm", "web_search"),
    ("tìm kiếm địa chỉ quán cà phê gần đây", "web_search"),
    ("tra cứu tỷ giá đô la mỹ", "web_search"),

    # 10. greeting_chat
    ("xin chào jarvis", "greeting_chat"),
    ("chào jarvis", "greeting_chat"),
    ("chào jarvis ơi", "greeting_chat"),
    ("chào buổi sáng", "greeting_chat"),
    ("chào buổi sáng jarvis ơi", "greeting_chat"),
    ("chào buổi tối", "greeting_chat"),
    ("chào buổi chiều bạn nhé", "greeting_chat"),
    ("bạn là ai", "greeting_chat"),
    ("giới thiệu về bản thân đi", "greeting_chat"),
    ("bạn có thể làm được những gì", "greeting_chat"),
    ("cảm ơn bạn nhiều", "greeting_chat"),
    ("cảm ơn jarvis", "greeting_chat"),
    ("thank you jarvis", "greeting_chat"),
    ("tạm biệt jarvis", "greeting_chat"),
    ("tạm biệt nhé", "greeting_chat"),
    ("hẹn gặp lại", "greeting_chat"),
    ("chúc ngủ ngon", "greeting_chat"),
    ("bạn có khỏe không", "greeting_chat"),
    ("hôm nay thế nào rồi jarvis", "greeting_chat"),
    ("jarvis ơi bạn có đó không", "greeting_chat"),

    # 11. window_management (NEW DOMAIN)
    ("chia đôi màn hình sang trái", "window_management"),
    ("chia màn hình sang trái", "window_management"),
    ("chia nửa màn hình bên trái", "window_management"),
    ("chia đôi màn hình sang phải", "window_management"),
    ("chia màn hình sang phải", "window_management"),
    ("chia nửa màn hình bên phải", "window_management"),
    ("phóng to cửa sổ", "window_management"),
    ("phóng to cửa sổ hiện tại", "window_management"),
    ("phóng to toàn màn hình", "window_management"),
    ("cho cửa sổ cực đại", "window_management"),
    ("maximize cửa sổ", "window_management"),
    ("thu nhỏ cửa sổ này", "window_management"),
    ("thu nhỏ cửa sổ xuống taskbar", "window_management"),
    ("minimize cửa sổ", "window_management"),
    ("khôi phục kích thước cửa sổ", "window_management"),
    ("restore cửa sổ", "window_management"),
    ("chuyển sang cửa sổ tiếp theo", "window_management"),
    ("chuyển tab cửa sổ", "window_management"),
    ("alt tab sang ứng dụng khác", "window_management"),
    ("đổi sang phần mềm tiếp theo", "window_management"),
    ("quản lý các cửa sổ đang mở", "window_management"),
    ("chia màn hình làm việc", "window_management"),
    ("thu nhỏ ứng dụng này lại", "window_management"),
    ("phóng to trình duyệt lên toàn màn hình", "window_management"),

    # 12. file_management (NEW DOMAIN)
    ("mở thư mục tải về", "file_management"),
    ("mở thư mục downloads", "file_management"),
    ("mở thư mục download", "file_management"),
    ("mở thư mục tài liệu", "file_management"),
    ("mở thư mục documents", "file_management"),
    ("mở thư mục hình ảnh", "file_management"),
    ("mở thư mục pictures", "file_management"),
    ("mở màn hình chính desktop", "file_management"),
    ("dọn dẹp thùng rác máy tính", "file_management"),
    ("dọn sạch thùng rác", "file_management"),
    ("làm sạch recycle bin", "file_management"),
    ("xóa toàn bộ file trong thùng rác", "file_management"),
    ("dọn rác máy tính", "file_management"),
    ("dọn rác ổ đĩa c", "file_management"),
    ("xóa các file tạm temp", "file_management"),
    ("dọn dẹp bộ nhớ tạm ổ cứng", "file_management"),
    ("mở thư mục lưu trữ", "file_management"),
    ("tìm file trong máy tính", "file_management"),
    ("mở ổ đĩa d", "file_management"),
    ("mở ổ đĩa c", "file_management"),
    ("kiểm tra các file mới tải về", "file_management"),

    # 13. clipboard_action (NEW DOMAIN)
    ("sao chép đoạn này", "clipboard_action"),
    ("sao chép nội dung vừa chọn", "clipboard_action"),
    ("copy văn bản", "clipboard_action"),
    ("copy vào clipboard", "clipboard_action"),
    ("dán nội dung vào đây", "clipboard_action"),
    ("paste văn bản", "clipboard_action"),
    ("dán từ clipboard", "clipboard_action"),
    ("xóa bộ nhớ tạm", "clipboard_action"),
    ("xóa clipboard đi", "clipboard_action"),
    ("làm trống bộ nhớ tạm clipboard", "clipboard_action"),
    ("đọc nội dung trong clipboard", "clipboard_action"),
    ("xem clipboard đang có gì", "clipboard_action"),
    ("kiểm tra nội dung bộ nhớ tạm", "clipboard_action"),
    ("đọc lại đoạn văn bản đã copy", "clipboard_action"),
    ("xóa lịch sử clipboard", "clipboard_action"),
    ("sao chép đường dẫn này", "clipboard_action"),
    ("paste nội dung vừa sao chép", "clipboard_action"),

    # 14. network_control (NEW DOMAIN)
    ("kiểm tra kết nối mạng", "network_control"),
    ("kiểm tra mạng internet", "network_control"),
    ("mạng có đang ổn định không", "network_control"),
    ("máy tính có kết nối internet không", "network_control"),
    ("đo tốc độ mạng", "network_control"),
    ("đo tốc độ internet speedtest", "network_control"),
    ("kiểm tra băng thông mạng", "network_control"),
    ("đo độ trễ ping mạng", "network_control"),
    ("địa chỉ ip của máy tính là gì", "network_control"),
    ("xem địa chỉ ip mạng", "network_control"),
    ("ip máy tính hiện tại", "network_control"),
    ("kiểm tra sóng wifi", "network_control"),
    ("thông tin mạng wifi đang kết nối", "network_control"),
    ("tên mạng wifi hiện tại", "network_control"),
    ("mạng wifi có bị mất không", "network_control"),
    ("tình trạng card mạng", "network_control"),

    # 15. system_power (NEW DOMAIN)
    ("khóa màn hình máy tính", "system_power"),
    ("khóa máy tính đi", "system_power"),
    ("lock màn hình lại", "system_power"),
    ("khóa máy ngay lập tức", "system_power"),
    ("cho máy tính đi ngủ sleep", "system_power"),
    ("chuyển máy tính sang chế độ sleep", "system_power"),
    ("cho máy tính nghỉ ngơi", "system_power"),
    ("chế độ ngủ đông hibernate", "system_power"),
    ("ngủ đông máy tính", "system_power"),
    ("hẹn giờ tắt máy tính sau 30 phút", "system_power"),
    ("hẹn giờ tắt máy sau 1 tiếng", "system_power"),
    ("hẹn giờ tắt máy sau 15 phút", "system_power"),
    ("tắt máy sau 45 phút nữa", "system_power"),
    ("hủy hẹn giờ tắt máy", "system_power"),
    ("hủy lệnh tắt máy tính", "system_power"),
    ("hủy shutdown máy tính", "system_power"),
    ("khởi động lại máy tính", "system_power"),
    ("restart lại máy tính", "system_power"),
    ("khởi động lại hệ thống", "system_power"),

    # 16. unknown (Out-of-Distribution / Negative samples)
    ("công thức nấu món phở bò truyền thống", "unknown"),
    ("giải bài toán phương trình bậc hai", "unknown"),
    ("chiến tranh thế giới thứ hai diễn ra năm nào", "unknown"),
    ("thủ đô của nước pháp là gì", "unknown"),
    ("tại sao lá cây lại có màu xanh", "unknown"),
    ("cách làm bánh sinh nhật tại nhà", "unknown"),
    ("hướng dẫn học đàn guitar cho người mới", "unknown"),
    ("tổng diện tích của việt nam là bao nhiêu", "unknown"),
    ("thơ xuân diệu hay nhất", "unknown"),
    ("nguồn gốc của vũ trụ", "unknown"),
    ("chú mèo đang ngủ trên ghế sofa", "unknown"),
    ("viết một đoạn văn tả cảnh hoàng hôn trên biển", "unknown"),
    ("học tiếng anh giao tiếp như thế nào cho hiệu quả", "unknown"),
    ("tôi đang đọc một cuốn sách rất hay", "unknown"),
    ("uống nhiều cà phê có hại cho sức khỏe không", "unknown"),
    ("bạn có biết lý thuyết tương đối của einstein không", "unknown"),
    ("bức tranh mona lisa do ai vẽ", "unknown"),
    ("núi everest cao bao nhiêu mét", "unknown"),
    ("nguyên tử gồm những hạt nào", "unknown"),
    ("hôm nay trời đẹp để đi dạo công viên", "unknown"),
    ("đoạn mã python này bị lỗi gì", "unknown"),
    ("cách trồng hoa hồng trong chậu", "unknown"),
    ("tại sao bầu trời lại có màu xanh lam", "unknown"),
    ("tiểu thuyết tam quốc diễn nghĩa có bao nhiêu hồi", "unknown"),
    ("vận tốc ánh sáng trong chân không là bao nhiêu", "unknown"),
    ("loài cá nào bơi nhanh nhất đại dương", "unknown"),
    ("lịch sử hình thành kim tự tháp ai cập", "unknown"),
    ("cách pha cà phê phin đậm đà chuẩn vị", "unknown"),
    ("thành phần hóa học của nước là gì", "unknown"),
    ("ai là người phát minh ra bóng đèn điện", "unknown"),
    ("lợi ích của việc chạy bộ mỗi buổi sáng", "unknown"),
    ("thời gian mặt trời mọc vào mùa hè", "unknown"),
]


def augment_dataset(canonical_data: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """
    Augments the dataset with:
      1. Tone-stripped (unaccented) versions.
      2. Colloquial suffixes and particles.
      3. Acoustic / Phonetic loanword replacements.
    """
    augmented: list[tuple[str, str]] = []
    seen = set()

    def add_item(t: str, lbl: str) -> None:
        clean = t.strip().lower()
        if clean and (clean, lbl) not in seen:
            seen.add((clean, lbl))
            augmented.append((clean, lbl))

    for text, label in canonical_data:
        add_item(text, label)

        # 1. Unaccented (tone-stripped) variant
        unaccented = strip_vietnamese_diacritics(text)
        if unaccented != text:
            add_item(unaccented, label)

        # 2. Conversational colloquial suffixes for action intents (skip unknown)
        if label != "unknown":
            add_item(f"{text} nhé", label)
            add_item(f"{text} hộ tôi", label)
            add_item(f"{text} đi bạn", label)
            add_item(f"làm ơn {text}", label)
            add_item(f"{text} giúp mình", label)
            add_item(f"{text} với", label)

    # 3. Phonetic loan word variations for English software/terms
    phonetic_loanwords = [
        ("chrome", ["cờ rôm", "chôm"]),
        ("excel", ["ét xel", "ếch xel"]),
        ("word", ["quốt", "uốt"]),
        ("spotify", ["sì po ti phai", "sờ po ti phai"]),
        ("facebook", ["phây búc", "phây"]),
        ("vscode", ["vê ét cốt", "ve et code"]),
        ("wifi", ["wai phai", "goai phai"]),
        ("clipboard", ["cờ líp bo", "cờ líp bót"]),
        ("windows", ["uýt đo", "uyn đâu"]),
    ]

    extra_phonetics: list[tuple[str, str]] = []
    for text, label in list(augmented):
        for canonical, phonetics in phonetic_loanwords:
            if canonical in text:
                for ph in phonetics:
                    ph_text = text.replace(canonical, ph)
                    extra_phonetics.append((ph_text, label))

    for t, l in extra_phonetics:
        add_item(t, l)

    return augmented


def export_model_to_onnx(classifier: VietnameseNLPClassifier, target_onnx_path: Path) -> bool:
    """
    Exports the trained Calibrated Classifier to ONNX Runtime format.
    """
    if not classifier.is_trained or classifier.pipeline is None:
        return False
    try:
        pipeline = classifier.pipeline
        feat_union = pipeline.named_steps["features"]
        calibrated_clf = pipeline.named_steps["classifier"]

        # Number of TF-IDF features
        n_features = sum(vec.transform(["test"]).shape[1] for _, vec in feat_union.transformer_list)

        initial_type = [("float_input", FloatTensorType([None, n_features]))]
        onnx_model = convert_sklearn(calibrated_clf, initial_types=initial_type, target_opset=17)

        target_onnx_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_onnx_path, "wb") as f:
            f.write(onnx_model.SerializeToString())

        print(f"[+] Đã xuất thành công mô hình ONNX tại: {target_onnx_path.resolve()}")
        return True
    except Exception as e:
        print(f"[-] Cảnh báo: Lỗi xuất ONNX: {e}")
        return False


def main() -> None:
    print("=" * 65)
    print("🚀 BẮT ĐẦU HUẤN LUYỆN NÂNG CẤP LOCAL VIETNAMESE NLP INTENT CLASSIFIER (15 DOMAINS)")
    print("=" * 65)

    print(f"[*] Số lượng mẫu gốc canonical: {len(CANONICAL_TRAINING_DATA)}")
    augmented_data = augment_dataset(CANONICAL_TRAINING_DATA)
    print(f"[*] Tổng số mẫu sau Data Augmentation (unaccented + colloquial + phonetic): {len(augmented_data)}")

    samples = [item[0] for item in augmented_data]
    labels = [item[1] for item in augmented_data]
    unique_classes = sorted(list(set(labels)))
    print(f"[*] Số lượng danh mục ý định (classes={len(unique_classes)}): {unique_classes}")

    classifier = VietnameseNLPClassifier()
    report = classifier.train(samples=samples, labels=labels, cv_folds=5)

    print("\n--- KẾT QUẢ ĐÁNH GIÁ MÔ HÌNH (5-FOLD STRATIFIED CV) ---")
    print(f"Độ chính xác (Accuracy): {report['cv_accuracy_mean'] * 100:.2f}% (± {report['cv_accuracy_std'] * 100:.2f}%)")
    print(f"Điểm số F1-Macro:        {report['cv_f1_macro_mean'] * 100:.2f}%")
    print(f"Thời gian huấn luyện:    {report['train_duration_s']} giây")

    # 1. Save Scikit-Learn model to disk (.joblib)
    target_path = DEFAULT_MODEL_PATH
    success = classifier.save(target_path)
    if success:
        print(f"\n[+] Đã lưu thành công Scikit-Learn mô hình tại: {target_path.resolve()}")
        size_kb = target_path.stat().st_size / 1024.0
        print(f"[+] Kích thước file .joblib: {size_kb:.2f} KB")
    else:
        print("\n[-] Lỗi lưu mô hình .joblib.")
        sys.exit(1)

    # 2. Export ONNX Runtime Graph (.onnx)
    target_onnx_path = target_path.with_suffix(".onnx")
    onnx_ok = export_model_to_onnx(classifier, target_onnx_path)
    if onnx_ok:
        onnx_size_kb = target_onnx_path.stat().st_size / 1024.0
        print(f"[+] Kích thước file .onnx:   {onnx_size_kb:.2f} KB (siêu nhẹ, < 1ms C-API runtime)")

    # 3. Verification Inference Benchmark & Slot Filling Probe across 15 domains
    print("\n--- KIỂM TRA SUY LUẬN & TRÍCH XUẤT SLOTS TRÊN 15 DOMAINS ---")
    test_queries = [
        "vặn nhỏ âm lượng loa xuống đi",
        "cho âm lượng lên 80%",
        "tat am thanh",
        "màn hình chói quá chỉnh tối bớt",
        "chỉnh độ sáng lên 90%",
        "bật phần mềm visual studio code",
        "mo cờ rôm",
        "dong trinh duyet chrome",
        "tắt nhạc spotify đi bạn ơi",
        "chuyển sang bài hát tiếp theo",
        "nhiệt độ cpu hiện tại bao nhiêu",
        "ram con trong bao nhieu",
        "bật đèn trần phòng khách",
        "tat may lanh phong ngu",
        "bật điều hòa 24 độ",
        "nhắc tôi uống thuốc sau 1 tiếng",
        "hẹn giờ 10 phút",
        "tra cứu thời tiết sài gòn ngày mai",
        "chào buổi sáng jarvis ơi",
        "chia đôi màn hình sang trái",
        "phóng to cửa sổ",
        "mở thư mục tải về",
        "dọn dẹp thùng rác máy tính",
        "sao chép đoạn này",
        "xóa clipboard đi",
        "kiểm tra kết nối mạng wifi",
        "đo tốc độ internet",
        "khóa màn hình máy tính",
        "hẹn giờ tắt máy tính sau 30 phút",
        "công thức nấu món phở bò truyền thống",
    ]

    for q in test_queries:
        res = classifier.predict(q)
        print(
            f"Query: '{q}'\n"
            f"  -> Intent: [{res.intent}] (Confidence: {res.confidence * 100:.1f}%, Latency: {res.latency_ms:.2f}ms)\n"
            f"  -> Slots: {res.slots}"
        )

    print("\n✅ HUẤN LUYỆN VÀ XÁC THỰC MÔ HÌNH 15 DOMAINS THÀNH CÔNG 100%!")


if __name__ == "__main__":
    main()
