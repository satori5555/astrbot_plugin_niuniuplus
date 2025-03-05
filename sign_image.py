import os
import datetime
import calendar
from PIL import Image, ImageDraw, ImageFont

class SignImageGenerator:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.lu_path = os.path.join(self.base_dir, 'lu.jpg')
        self.deer_path = os.path.join(self.base_dir, 'deer_1f98c.png')
        self.check_mark_path = os.path.join(self.base_dir, 'heavy-check-mark_2714.png')
        self.signimg_dir = os.path.join(self.base_dir, 'signimg')
        self.record_path = os.path.join(self.base_dir, 'signrecord.txt')
        os.makedirs(self.signimg_dir, exist_ok=True)

    def get_month_name(self):
        return datetime.datetime.now().strftime('%B')

    def get_sign_image_path(self, group_id=None):
        month = self.get_month_name()
        if group_id:
            return os.path.join(self.signimg_dir, f'sign{month}_{group_id}.png')
        else:
            return os.path.join(self.signimg_dir, f'sign{month}.png')

    def load_sign_records(self, user_id, group_id):
        if not os.path.exists(self.record_path):
            return set()
        records = set()
        
        # 获取当前年月
        now = datetime.datetime.now()
        current_year = now.year
        current_month = now.month
        
        try:
            with open(self.record_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        parts = line.strip().split(',')
                        if len(parts) == 3:  # 确保记录格式正确
                            date, uid, gid = parts
                            # 确保类型一致性
                            if str(uid) == str(user_id) and str(gid) == str(group_id):
                                try:
                                    # 解析日期
                                    date_parts = date.split('-')
                                    year = int(date_parts[0])
                                    month = int(date_parts[1])
                                    day = int(date_parts[2])
                                    
                                    # 只添加当前年月的记录
                                    if year == current_year and month == current_month:
                                        records.add(day)
                                except (IndexError, ValueError):
                                    print(f"Invalid date format: {date}")
        except Exception as e:
            print(f"Error loading sign records: {e}")
        return records

    def save_sign_record(self, user_id, group_id):
        current_date = datetime.datetime.now().strftime('%Y-%m-%d')
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.record_path), exist_ok=True)
            # 以追加模式打开文件，如果文件不存在则创建
            with open(self.record_path, 'a', encoding='utf-8') as f:
                f.write(f"{current_date},{user_id},{group_id}\n")
        except Exception as e:
            print(f"Error saving sign record: {e}")

    def generate_sign_image(self, nickname, coins):
        # 检查lu.jpg是否存在
        if not os.path.exists(self.lu_path):
            raise FileNotFoundError("lu.jpg not found")

        # 创建基础图像
        width = 800
        height = 1100
        image = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(image)

        # 尝试多个可能的字体路径
        font = None
        font_paths = [
            os.path.join(self.base_dir, 'SimHei.ttf'),
            os.path.join(self.base_dir, 'fonts', 'SimHei.ttf'),
            'C:\\Windows\\Fonts\\SimHei.ttf'
        ]
        
        for font_path in font_paths:
            try:
                if os.path.exists(font_path):
                    font = ImageFont.truetype(font_path, 32)
                    print(f"成功加载字体: {font_path}")
                    break
            except Exception as e:
                print(f"加载字体失败 {font_path}: {str(e)}")
                continue
        
        if font is None:
            print("警告: 无法加载SimHei字体，使用默认字体")
            font = ImageFont.load_default()

        # 绘制标题
        title_text_1 = "今天你"
        title_text_2 = "了吗？"
        # 计算文本宽度
        title_text_1_width = font.getsize(title_text_1)[0] if hasattr(font, 'getsize') else font.getbbox(title_text_1)[2]
        title_text_2_width = font.getsize(title_text_2)[0] if hasattr(font, 'getsize') else font.getbbox(title_text_2)[2]
        
        # 计算标题总宽度（包括图片）
        deer_size = font.getsize("鹿")[1] if hasattr(font, 'getsize') else font.getbbox("鹿")[3]
        total_width = title_text_1_width + deer_size + title_text_2_width
        
        # 计算起始位置
        start_x = (width - total_width) // 2
        
        # 绘制第一部分文本
        draw.text((start_x, 20), title_text_1, font=font, fill='black')
        
        # 插入鹿图片
        if os.path.exists(self.deer_path):
            deer_img = Image.open(self.deer_path)
            deer_img = deer_img.resize((deer_size, deer_size))
            image.paste(deer_img, (start_x + title_text_1_width, 20), deer_img if deer_img.mode == 'RGBA' else None)
        
        # 绘制第二部分文本
        draw.text((start_x + title_text_1_width + deer_size, 20), title_text_2, font=font, fill='black')

        # 绘制用户信息
        current_date = datetime.datetime.now().strftime('%Y年%m月%d日')
        draw.text((20, 80), f"用户：{nickname}", font=font, fill='black')
        draw.text((20, 130), f"日期：{current_date}", font=font, fill='black')
        
        # 绘制签到信息
        sign_text_1 = "今天你成功"
        sign_text_2 = "了，获得"
        sign_text_3 = f"{coins}金币"
        
        # 计算文本宽度
        sign_text_1_width = font.getsize(sign_text_1)[0] if hasattr(font, 'getsize') else font.getbbox(sign_text_1)[2]
        sign_text_2_width = font.getsize(sign_text_2)[0] if hasattr(font, 'getsize') else font.getbbox(sign_text_2)[2]
        
        # 绘制签到文本和图片
        x = 20
        draw.text((x, 180), sign_text_1, font=font, fill='black')
        x += sign_text_1_width
        
        if os.path.exists(self.deer_path):
            deer_img = Image.open(self.deer_path)
            deer_img = deer_img.resize((deer_size, deer_size))
            image.paste(deer_img, (x, 180), deer_img if deer_img.mode == 'RGBA' else None)
        
        x += deer_size
        draw.text((x, 180), sign_text_2 + sign_text_3, font=font, fill='black')

        # 加载鹿图片
        lu_img = Image.open(self.lu_path)
        lu_size = 100
        lu_img = lu_img.resize((lu_size, lu_size))

        # 获取当月日历
        now = datetime.datetime.now()
        cal = calendar.monthcalendar(now.year, now.month)

        # 绘制日历
        start_y = 250
        for week in cal:
            x = 20
            for day in week:
                if day != 0:
                    # 粘贴鹿图片
                    image.paste(lu_img, (x, start_y))
                    # 添加日期数字
                    day_str = str(day)
                    # 兼容不同版本的PIL
                    try:
                        # 尝试使用新版PIL的getbbox方法
                        bbox = font.getbbox(day_str)
                        day_width = bbox[2] - bbox[0]
                    except AttributeError:
                        # 回退到旧版PIL的getsize方法
                        day_width, _ = font.getsize(day_str)
                    draw.text((x + (lu_size - day_width) // 2, start_y + lu_size), 
                             day_str, font=font, fill='black')

                    # 如果是今天的日期，添加签到标记
                    if day == now.day:
                        if os.path.exists(self.check_mark_path):
                            check_img = Image.open(self.check_mark_path)
                            check_size = lu_size // 2  # 设置勾的大小为鹿图片的一半
                            check_img = check_img.resize((check_size, check_size))
                            # 计算勾的位置，使其居中显示在鹿图片上
                            check_x = x + (lu_size - check_size) // 2
                            check_y = start_y + (lu_size - check_size) // 2
                            image.paste(check_img, (check_x, check_y), check_img if check_img.mode == 'RGBA' else None)
                    x += lu_size + 10
                    # 如果是已签到的日期，添加签到标记
                    if day in sign_records:
                        if os.path.exists(self.check_mark_path):
                            check_img = Image.open(self.check_mark_path)
                            check_size = lu_size // 2  # 设置勾的大小为鹿图片的一半
                            check_img = check_img.resize((check_size, check_size))
                            # 计算勾的位置，使其居中显示在鹿图片上
                            check_x = x + (lu_size - check_size) // 2
                            check_y = start_y + (lu_size - check_size) // 2
                            image.paste(check_img, (check_x, check_y), check_img if check_img.mode == 'RGBA' else None)
                x += lu_size + 10
            start_y += lu_size + 40

        return image

    def create_sign_image(self, nickname, coins, group_id=None):
        # 生成签到图片
        image = self.generate_sign_image(nickname, coins)
        
        # 保存图片
        save_path = self.get_sign_image_path(group_id)
        image.save(save_path)
        return save_path

    def generate_calendar_image(self, nickname, user_id, group_id):
        # 检查lu.jpg是否存在
        if not os.path.exists(self.lu_path):
            raise FileNotFoundError("lu.jpg not found")

        # 创建基础图像
        width = 800
        height = 1100
        image = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(image)

        # 尝试多个可能的字体路径
        font = None
        font_paths = [
            os.path.join(self.base_dir, 'SimHei.ttf'),
            os.path.join(self.base_dir, 'fonts', 'SimHei.ttf'),
            'C:\\Windows\\Fonts\\SimHei.ttf'
        ]
        
        for font_path in font_paths:
            try:
                if os.path.exists(font_path):
                    font = ImageFont.truetype(font_path, 32)
                    print(f"成功加载字体: {font_path}")
                    break
            except Exception as e:
                print(f"加载字体失败 {font_path}: {str(e)}")
                continue
        
        if font is None:
            print("警告: 无法加载SimHei字体，使用默认字体")
            font = ImageFont.load_default()

        # 绘制标题
        title = "本月关记录"
        # 兼容不同版本的PIL
        try:
            # 尝试使用新版PIL的getbbox方法
            bbox = font.getbbox(title)
            title_width = bbox[2] - bbox[0]
        except AttributeError:
            # 回退到旧版PIL的getsize方法
            title_width, _ = font.getsize(title)
        
        # 计算标题位置
        title_x = (width - title_width - font.getsize("鹿")[1] if hasattr(font, 'getsize') else font.getbbox("鹿")[3]) // 2
        title_y = 20
        
        # 绘制标题文本的第一部分"本月"
        # 绘制标题
        month_text = "本月"
        record_text = "关记录"
        # 计算文本宽度
        month_width = font.getsize(month_text)[0] if hasattr(font, 'getsize') else font.getbbox(month_text)[2]
        record_width = font.getsize(record_text)[0] if hasattr(font, 'getsize') else font.getbbox(record_text)[2]
        deer_size = font.getsize("鹿")[1] if hasattr(font, 'getsize') else font.getbbox("鹿")[3]
        
        # 计算总宽度（月 + 鹿 + 关记录）
        total_width = month_width + deer_size + record_width
        
        # 计算起始位置以居中显示
        title_x = (width - total_width) // 2
        title_y = 20
        
        # 绘制第一部分文本
        draw.text((title_x, title_y), month_text, font=font, fill='black')
        
        # 在"本月"后面插入鹿图片
        if os.path.exists(self.deer_path):
            deer_img = Image.open(self.deer_path)
            deer_img = deer_img.resize((deer_size, deer_size))
            image.paste(deer_img, (title_x + month_width, title_y), deer_img if deer_img.mode == 'RGBA' else None)
            
            # 绘制"关记录"部分
            draw.text((title_x + month_width + deer_size, title_y), record_text, font=font, fill='black')

        # 加载用户签到记录
        sign_records = self.load_sign_records(user_id, group_id)
        sign_count = len(sign_records)

        # 绘制用户信息
        now = datetime.datetime.now()
        current_month = now.strftime('%Y年%m月')
        draw.text((20, 80), f"用户：{nickname}", font=font, fill='black')
        # 绘制签到次数文本
        sign_text_1 = "本月"
        sign_text_2 = f"关{sign_count}次"
        
        # 计算文本宽度
        sign_text_1_width = font.getsize(sign_text_1)[0] if hasattr(font, 'getsize') else font.getbbox(sign_text_1)[2]
        
        # 绘制第一部分文本
        draw.text((20, 130), sign_text_1, font=font, fill='black')
        
        # 插入鹿图片
        if os.path.exists(self.deer_path):
            deer_img = Image.open(self.deer_path)
            deer_size = font.getsize("鹿")[1] if hasattr(font, 'getsize') else font.getbbox("鹿")[3]
            deer_img = deer_img.resize((deer_size, deer_size))
            image.paste(deer_img, (20 + sign_text_1_width, 130), deer_img if deer_img.mode == 'RGBA' else None)
        
        # 绘制第二部分文本
        draw.text((20 + sign_text_1_width + deer_size, 130), sign_text_2, font=font, fill='black')
        
        # 绘制"你就是鹿关大师！"文本，将"鹿"替换为图片
        master_text_1 = "你就是"
        master_text_2 = "关大师！"
        master_text_1_width = font.getsize(master_text_1)[0] if hasattr(font, 'getsize') else font.getbbox(master_text_1)[2]
        
        # 绘制第一部分文本
        draw.text((20, 180), master_text_1, font=font, fill='black')
        
        # 插入鹿图片
        if os.path.exists(self.deer_path):
            deer_img = Image.open(self.deer_path)
            deer_img = deer_img.resize((deer_size, deer_size))
            image.paste(deer_img, (20 + master_text_1_width, 180), deer_img if deer_img.mode == 'RGBA' else None)
        
        # 绘制第二部分文本
        draw.text((20 + master_text_1_width + deer_size, 180), master_text_2, font=font, fill='black')

        # 加载鹿图片
        lu_img = Image.open(self.lu_path)
        lu_size = 100
        lu_img = lu_img.resize((lu_size, lu_size))

        # 获取当月日历
        cal = calendar.monthcalendar(now.year, now.month)

        # 绘制日历
        start_y = 250
        for week in cal:
            x = 20
            for day in week:
                if day != 0:
                    # 粘贴鹿图片
                    image.paste(lu_img, (x, start_y))
                    # 添加日期数字
                    day_str = str(day)
                    # 兼容不同版本的PIL
                    try:
                        # 尝试使用新版PIL的getbbox方法
                        bbox = font.getbbox(day_str)
                        day_width = bbox[2] - bbox[0]
                    except AttributeError:
                        # 回退到旧版PIL的getsize方法
                        day_width, _ = font.getsize(day_str)
                    draw.text((x + (lu_size - day_width) // 2, start_y + lu_size), 
                             day_str, font=font, fill='black')

                    # 如果是已签到的日期，添加签到标记
                    if day in sign_records:
                        if os.path.exists(self.check_mark_path):
                            check_img = Image.open(self.check_mark_path)
                            check_size = lu_size // 2  # 设置勾的大小为鹿图片的一半
                            check_img = check_img.resize((check_size, check_size))
                            # 计算勾的位置，使其居中显示在鹿图片上
                            check_x = x + (lu_size - check_size) // 2
                            check_y = start_y + (lu_size - check_size) // 2
                            image.paste(check_img, (check_x, check_y), check_img if check_img.mode == 'RGBA' else None)
                x += lu_size + 10
            start_y += lu_size + 40

        return image

    def create_calendar_image(self, nickname, user_id, group_id):
        # 生成日历图片
        image = self.generate_calendar_image(nickname, user_id, group_id)
        
        # 保存图片
        month = self.get_month_name()
        calendar_path = os.path.join(self.signimg_dir, f'calendar{month}_{group_id}.png')
        image.save(calendar_path)
        return calendar_path