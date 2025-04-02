import os
import yaml
from typing import Tuple, List
from astrbot.api.message_components import At, Plain

class TaxSystem:
    """税收系统类，管理金币获取时的税收"""
    
    def __init__(self, plugin):
        """初始化税收系统
        
        Args:
            plugin: NiuniuPlugin实例的引用
        """
        self.plugin = plugin
        # 修改为data目录下的路径，确保数据不会在更新时被覆盖
        self.tax_file = os.path.join('data', 'niuniu_tax.yml')
        self.tax_data = self._load_tax_data()
        
        # 确保groups字典存在
        if 'groups' not in self.tax_data:
            self.tax_data['groups'] = {}
        
        # 初始化赋税开关状态
        if 'tax_enabled' not in self.tax_data:
            self.tax_data['tax_enabled'] = {}
        
        # 保存初始数据
        self._save_tax_data()
        
    def _load_tax_data(self) -> dict:
        """加载税收数据"""
        if not os.path.exists(self.tax_file):
            return {'groups': {}}
        
        try:
            with open(self.tax_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if not data:
                    data = {'groups': {}}
                elif not isinstance(data.get('groups'), dict):
                    data['groups'] = {}
                    
            return data
        except Exception as e:
            logger.error(f"加载税收数据失败: {str(e)}")
            return {'groups': {}}
            
    def _save_tax_data(self):
        """保存税收数据"""
        try:
            os.makedirs(os.path.dirname(self.tax_file), exist_ok=True)
            with open(self.tax_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.tax_data, f, allow_unicode=True)
        except Exception as e:
            logger.error(f"保存税收数据失败: {str(e)}")
            
    def calculate_tax(self, amount: int) -> Tuple[int, int]:
        """计算应缴税额
        
        Args:
            amount: 获得的金币数量
            
        Returns:
            Tuple[int, int]: (税后金额, 税额)
        """
        if amount <= 0:
            return 0, 0
            
        # 计算税率
        if amount < 100:
            tax_rate = 0.05  # 5%
        elif amount < 1000:
            tax_rate = 0.10  # 10%
        elif amount < 5000:
            tax_rate = 0.20  # 20%
        else:
            tax_rate = 0.30  # 30%
            
        # 计算税额（向上取整）
        tax = int(amount * tax_rate + 0.5)
        # 计算税后金额
        after_tax = amount - tax
        
        return after_tax, tax
        
    def add_tax_to_treasury(self, group_id: str, tax_amount: int):
        """将税收添加到群公共账户
        
        Args:
            group_id: 群ID
            tax_amount: 税额
        """
        if not isinstance(group_id, str):
            group_id = str(group_id)
            
        if group_id not in self.tax_data['groups']:
            self.tax_data['groups'][group_id] = 0
            
        self.tax_data['groups'][group_id] += tax_amount
        self._save_tax_data()
        
    def get_treasury_balance(self, group_id: str) -> int:
        """获取群公共账户余额
        
        Args:
            group_id: 群ID
            
        Returns:
            int: 公共账户余额
        """
        if not isinstance(group_id, str):
            group_id = str(group_id)
            
        return self.tax_data['groups'].get(group_id, 0)
        
    def process_coins(self, group_id: str, amount: int) -> Tuple[int, int]:
        """处理金币获取，计算税收并更新公共账户
        
        Args:
            group_id: 群ID
            amount: 获得的金币数量
            
        Returns:
            Tuple[int, int]: (税后金额, 税额)
        """
        # 检查赋税是否开启
        if not self.is_tax_enabled(group_id):
            return amount, 0  # 赋税未开启，返回全额金币
            
        after_tax, tax = self.calculate_tax(amount)
        if tax > 0:
            self.add_tax_to_treasury(group_id, tax)
        return after_tax, tax
        
    def show_treasury_menu(self) -> str:
        """显示群账户菜单"""
        menu = [
            "💰 群账户功能菜单：",
            "📊 群账户 - 查看群账户余额",
            "💸 群账户 发工资 [金额] - 使用群账户余额发放工资（平分）",
            "💵 群账户 转账 @用户 [金额] - 使用群账户余额转账给指定用户",
            "🔄 开启赋税/关闭赋税 - 控制是否收税",
            "",
            "⚠️ 注意：只有管理员才能使用群账户功能"
        ]
        return "\n".join(menu)
        
    def distribute_salary(self, group_id: str, total_amount: int) -> Tuple[bool, str]:
        """发放工资
        
        Args:
            group_id: 群ID
            total_amount: 总金额
            
        Returns:
            Tuple[bool, str]: (是否成功, 结果信息)
        """
        # 检查群账户余额
        balance = self.get_treasury_balance(group_id)
        if balance < total_amount:
            return False, f"❌ 群账户余额不足，当前余额：{balance}金币"
            
        # 获取群内所有注册用户
        group_data = self.plugin.get_group_data(group_id)
        registered_users = []
        for user_id, user_data in group_data.items():
            if isinstance(user_data, dict) and 'nickname' in user_data:
                registered_users.append((user_id, user_data))
                
        if not registered_users:
            return False, "❌ 群内没有注册用户"
            
        # 计算每人获得的金额
        amount_per_person = total_amount // len(registered_users)
        if amount_per_person <= 0:
            return False, "❌ 每人获得的金额必须大于0"
            
        # 发放工资
        for user_id, user_data in registered_users:
            user_data['coins'] = user_data.get('coins', 0) + amount_per_person
            
        # 扣除群账户余额
        self.tax_data['groups'][group_id] -= total_amount
        self._save_tax_data()
        self.plugin._save_niuniu_lengths()
        
        return True, f"✅ 成功发放工资！\n总金额：{total_amount}金币\n每人获得：{amount_per_person}金币\n当前群账户余额：{self.get_treasury_balance(group_id)}金币"
        
    def transfer_to_user(self, group_id: str, target_id: str, amount: int) -> Tuple[bool, str]:
        """转账给指定用户
        
        Args:
            group_id: 群ID
            target_id: 目标用户ID
            amount: 转账金额
            
        Returns:
            Tuple[bool, str]: (是否成功, 结果信息)
        """
        # 检查群账户余额
        balance = self.get_treasury_balance(group_id)
        if balance < amount:
            return False, f"❌ 群账户余额不足，当前余额：{balance}金币"
            
        # 检查目标用户是否存在
        target_data = self.plugin.get_user_data(group_id, target_id)
        if not target_data:
            return False, "❌ 目标用户不存在"
            
        # 执行转账
        target_data['coins'] = target_data.get('coins', 0) + amount
        self.tax_data['groups'][group_id] -= amount
        self._save_tax_data()
        self.plugin._save_niuniu_lengths()
        
        target_nickname = target_data.get('nickname', '未知用户')
        return True, f"✅ 成功转账！\n金额：{amount}金币\n接收者：{target_nickname}\n当前群账户余额：{self.get_treasury_balance(group_id)}金币"
        
    def is_tax_enabled(self, group_id: str) -> bool:
        """检查群组的赋税是否开启
        
        Args:
            group_id: 群ID
            
        Returns:
            bool: 赋税是否开启
        """
        if not isinstance(group_id, str):
            group_id = str(group_id)
            
        # 默认开启赋税
        return self.tax_data.get('tax_enabled', {}).get(group_id, True)
        
    def set_tax_status(self, group_id: str, enabled: bool) -> None:
        """设置群组的赋税状态
        
        Args:
            group_id: 群ID
            enabled: 是否开启赋税
        """
        if not isinstance(group_id, str):
            group_id = str(group_id)
            
        if 'tax_enabled' not in self.tax_data:
            self.tax_data['tax_enabled'] = {}
            
        self.tax_data['tax_enabled'][group_id] = enabled
        self._save_tax_data() 