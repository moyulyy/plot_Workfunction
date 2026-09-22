# 示例作业（test）

一份 VASP 功函数计算的精简输出，用于演示 `WF · 功函数绘图工作台`。

## 内容

| 文件 | 说明 |
| :--- | :--- |
| `PLANAR_AVERAGE.dat` | vaspkit 426 沿 c 方向的平面平均势（240 点） |
| `cmd.log` | vaspkit 输出：`Vacuum-Level 4.202 eV` / `Work Function 5.762 eV` / `E-fermi -1.56 eV` |
| `OUTCAR` | 含 `E-fermi`，用于 `cmd.log` 缺失时兜底 |
| `POSCAR` / `CONTCAR` | 结构（晶格 c = 23.0 Å） |
| `INCAR` / `KPOINTS` / `POTCAR` | 计算输入 |

## 结果

| 项目 | 数值 |
| :--- | :--- |
| 体系 | O48Mn24Co6Co6（84 原子） |
| 晶格 c | 23.0000 Å |
| E_F | −1.5600 eV |
| V_vac | 4.2020 eV |
| **Φ** | **5.7620 eV** |

## 使用

```bash
# 源码运行
python wf_viewer.py test

# 便携版
WF-Viewer.exe test
```

> 体积巨大的原始产物（`POT` / `CHGCAR` / `LOCPOT` / `vasprun.xml` / `PROCAR` 等）
> 已通过 `.gitignore` 排除，绘图与计算演示无需这些文件。
