import subprocess
import time
from datetime import datetime
import csv
import sys
from collections import defaultdict

class PhoneRebootTester:
    def __init__(self, test_cycles=1000, output_file='reboot_test_results.csv'):
        """
        初始化重启测试器
        :param test_cycles: 测试循环次数 (默认1000次)
        :param output_file: 结果输出文件名 (默认'reboot_test_results.csv')
        """
        self.test_cycles = test_cycles
        self.output_file = output_file
        self.results = []
        self.current_cycle = 0
        self.device_serial = None
        self.error_stats = defaultdict(int)  # 用于统计各类错误出现次数
        
        # 初始化错误类型分类
        self.error_types = {
            "adb_connection": "ADB连接失败",
            "reboot_timeout": "重启命令超时",
            "boot_timeout": "启动超时",
            "device_not_found": "设备未连接",
            "boot_failure": "启动失败",
            "unknown_error": "未知错误"
        }
        
        self._check_adb()
        self._check_device()

    def _check_adb(self):
        """检查ADB是否安装并可用"""
        try:
            subprocess.run(['adb', 'version'], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("错误: ADB未找到或不可用。请安装Android SDK并确保adb在PATH中。")
            sys.exit(1)

    def _check_device(self):
        """检查设备是否连接"""
        result = subprocess.run(['adb', 'devices'], capture_output=True, text=True)
        devices = [line.split('\t')[0] for line in result.stdout.split('\n')[1:] if line.strip()]
        
        if not devices:
            print("错误: 未找到连接的设备。请连接设备并启用USB调试。")
            sys.exit(1)
        elif len(devices) > 1:
            print("警告: 检测到多个设备，将使用第一个设备:", devices[0])

        self.device_serial = devices[0]
        print(f"已连接设备: {self.device_serial}")

    def _execute_adb_command(self, command, timeout=30):
        """执行ADB命令并返回结果"""
        full_command = ['adb', '-s', self.device_serial] + command
        try:
            result = subprocess.run(
                full_command,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return True, result.stdout.strip()
        except subprocess.CalledProcessError as e:
            error_type = self._classify_error(e.stderr.strip())
            return False, error_type
        except subprocess.TimeoutExpired:
            return False, "reboot_timeout"
        except Exception as e:
            return False, "unknown_error"

    def _classify_error(self, error_msg):
        """分类识别错误类型"""
        error_msg = error_msg.lower()
        if "device not found" in error_msg:
            return "device_not_found"
        elif "timeout" in error_msg or "timed out" in error_msg:
            return "reboot_timeout"
        elif "error" in error_msg or "fail" in error_msg:
            return "adb_connection"
        else:
            return "unknown_error"

    def _wait_for_boot_completion(self, timeout=180):
        """等待设备启动完成"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            success, output = self._execute_adb_command(['shell', 'getprop', 'sys.boot_completed'], timeout=10)
            if success and output == '1':
                return True, "boot_success"
            time.sleep(5)
        return False, "boot_timeout"

    def perform_reboot(self):
        """执行一次完整的重启测试并记录详细异常信息"""
        test_result = {
            'cycle': self.current_cycle + 1,
            'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'reboot_success': False,
            'boot_success': False,
            'error_type': None,
            'error_message': None,
            'duration_seconds': None,
            'end_time': None
        }

        try:
            print(f"\n开始测试循环 #{test_result['cycle']}/{self.test_cycles}")
            start_time = time.time()
            
            # 执行重启命令
            print("执行重启...")
            success, error_type = self._execute_adb_command(['reboot'])
            if not success:
                test_result['error_type'] = error_type
                test_result['error_message'] = self.error_types.get(error_type, "未知错误")
                self.error_stats[error_type] += 1
                self.results.append(test_result)
                return False
            
            test_result['reboot_success'] = True
            
            # 等待设备重启完成
            print("等待设备重启...")
            boot_success, boot_status = self._wait_for_boot_completion()
            
            if not boot_success:
                test_result['error_type'] = boot_status
                test_result['error_message'] = self.error_types.get(boot_status, "未知启动错误")
                self.error_stats[boot_status] += 1
                self.results.append(test_result)
                return False
            
            test_result['boot_success'] = True
            test_result['duration_seconds'] = round(time.time() - start_time, 2)
            test_result['end_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            print(f"重启测试 #{test_result['cycle']} 完成, 耗时 {test_result['duration_seconds']}秒")
            self.results.append(test_result)
            return True
            
        except Exception as e:
            error_type = "unknown_error"
            test_result['error_type'] = error_type
            test_result['error_message'] = f"未分类异常: {str(e)}"
            self.error_stats[error_type] += 1
            self.results.append(test_result)
            return False

    def save_results(self):
        """将测试结果保存到CSV文件（解决中文乱码版本）"""
        if not self.results:
            print("没有测试结果可保存")
            return False

        try:
            with open(self.output_file, mode='w', newline='', encoding='utf-8-sig') as f:
                fieldnames = [
                    'cycle', 
                    'start_time', 
                    'end_time',
                    'reboot_success',
                    'boot_success',
                    'error_type',
                    'error_message',
                    'duration_seconds'
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.results)
            
            print(f"\n测试结果已保存到 {self.output_file}")
            return True
        except Exception as e:
            print(f"保存结果失败: {e}")
            return False

    def print_summary(self):
        """打印测试摘要和错误统计"""
        if not self.results:
            print("没有可用的测试结果")
            return

        total = len(self.results)
        success = sum(1 for r in self.results if r['reboot_success'] and r['boot_success'])
        failures = total - success

        print("\n测试摘要:")
        print(f"总测试次数: {total}")
        print(f"成功次数: {success}")
        print(f"失败次数: {failures}")
        print(f"成功率: {success/total*100:.2f}%")

        if self.error_stats:
            print("\n错误统计:")
            for error_type, count in sorted(self.error_stats.items(), key=lambda x: x[1], reverse=True):
                print(f"{self.error_types.get(error_type, '未知错误')}: {count}次 ({(count/total)*100:.1f}%)")

    def run(self):
        """运行完整的测试套件"""
        print(f"开始手机重启压力测试，共 {self.test_cycles} 次循环")
        print("按Ctrl+C可中断测试\n")

        try:
            while self.current_cycle < self.test_cycles:
                self.perform_reboot()
                self.current_cycle += 1
                
                # 每10次循环保存一次中间结果
                if self.current_cycle % 10 == 0:
                    self.save_results()
                    self.print_summary()  # 定期显示进度
                
                # 短暂的冷却时间
                time.sleep(2)
                
        except KeyboardInterrupt:
            print("\n测试被用户中断")
        except Exception as e:
            print(f"\n测试遇到错误: {e}")
        finally:
            self.save_results()
            self.print_summary()


if __name__ == '__main__':
    tester = PhoneRebootTester(test_cycles=1000)
    tester.run()