# radar-analysis-tool

毫米波雷达分析工具，支持从日志文本生成中英双语 HTML 测试报告，并提供桌面 GUI 一键生成。

## 功能说明

- 解析 [HEAD] / [Point] / [Object] 帧数据。
- 输出目标周期统计（支持中途丢跟踪后按纵向距离连续性归并同周期）。
- 输出点云匹配、建航帧数、目标丢失与缺失帧分析。
- 输出报警分析：
	- 报警起始帧与类型（0: 无报警，1: 左，2: 右）
	- 最远报警距离
	- 丢失报警帧（应连续报警但出现 0）
	- 报警提示切换距离
- 报告为中英双语字段。

## Python 脚本

- 主分析脚本：[generate_radar_report.py](generate_radar_report.py)
- GUI 入口脚本：[radar_report_gui.py](radar_report_gui.py)

### 命令行生成报告

```powershell
python .\generate_radar_report.py -i .\frame.txt -o .\report.html
```

## GUI 使用方式

```powershell
python .\radar_report_gui.py
```

界面流程：

1. 选择输入 frame.txt。
2. 选择报告输出路径（默认 report.html）。
3. 点击“生成测试报告 / Generate Test Report”。
4. 生成完成后弹窗提示成功，并显示报告路径。

## 打包 exe

项目使用 PyInstaller 打包，并指定版本配置文件 [tapp_versionfile.txt](tapp_versionfile.txt)：

```powershell
python -m PyInstaller --noconfirm --clean --onefile --windowed --name RadarReportApp --version-file .\tapp_versionfile.txt .\radar_report_gui.py
```

生成结果：

- [dist/RadarReportApp.exe](dist/RadarReportApp.exe)
