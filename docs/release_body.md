## ⚡ WF · 功函数绘图工作台 v1.0.0

首个正式版本 —— 一键把 VASP 功函数计算输出变成可发表级平面平均势曲线。

<div align="center">
  <img src="https://raw.githubusercontent.com/moyulyy/plot_Workfunction/main/docs/ui.png" alt="界面预览" width="820">
</div>

### ✨ 亮点

- **一键加载**：选择一次作业文件夹，自动识别 `PLANAR_AVERAGE.dat`、`cmd.log`、`OUTCAR`、`vasprun.xml`、`POSCAR`
- **专业制图**：平面平均势 `V(z)` 曲线，自动标注 **Fermi level / vacuum level** 与功函数 **Φ** 双箭头
- **数值可靠**：优先取 `cmd.log` 中 vaspkit 数值；缺失时按两端平台平均自动兜底（Φ = V_vac − E_F）
- **参数可调**：横/纵轴区间与刻度、费米/真空能级、线宽、颜色、标注字号，实时重绘
- **深浅主题**：标题栏一键切换，图表同步换色
- **高清导出**：300 dpi PNG / PDF / SVG / JPEG

### 📦 下载

| 文件 | 说明 |
| :--- | :--- |
| **`WF-Viewer-v1.0.0-win64.zip`** | Windows 便携版，解压后双击 `WF-Viewer.exe`，无需安装 Python |

### 🖥️ 运行环境

- Windows 10 / 11（64-bit）
- 已内置 Python 运行时与 PySide6 / matplotlib / numpy

### 🚀 使用方法

1. 下载并解压 `WF-Viewer-v1.0.0-win64.zip`
2. 双击 `WF-Viewer.exe`
3. 点击右栏「选择作业文件夹」，选择包含 `PLANAR_AVERAGE.dat` 的 VASP 功函数作业目录
4. 调整参数后点击「保存图片」导出高清图

> 也可把作业目录作为参数传入：`WF-Viewer.exe "D:\path\to\workfunction"`，启动即自动加载。

### 📊 示例作业

内置示例（`test/`）验证结果：**Φ = 5.7620 eV**，与 `cmd.log` 中 vaspkit 打印的
`Vacuum-Level (eV): 4.202` / `Work Function (eV): 5.762` 完全一致。

### 📄 文件校验（SHA-256）

```
6d4823888932608ad2046660c31d2fb8cc47739653b73d9f783cf83bff66671a  WF-Viewer-v1.0.0-win64.zip
```

---

**完整文档**：https://github.com/moyulyy/plot_Workfunction#readme
