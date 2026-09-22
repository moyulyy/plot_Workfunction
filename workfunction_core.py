#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
功函数（Work Function）数据处理核心
=====================================

移植 / 归并自两处既有实现：

* ``Web_Probe`` 后端 ``backend/app/routers/users.py`` 的 work_function 流程：
    - vaspkit 426（Potential Analysis）输出的 ``PLANAR_AVERAGE.dat``（z 与平面平均势）
    - 从 ``cmd.log`` 检索 ``E-fermi`` / ``Vacuum-Level`` / ``Work Function``
    - 检索不到时兜底：真空能级取两端平台中较高一侧的平均，Φ = V_vac − E_F
* ``workfunction-bot`` 的计算约定：LVHAR / LDIPOL / IDIPOL=3 输出 LOCPOT，
  再由 vaspkit 426 沿 c 方向做平面平均。

本模块只负责「读文件 → 结构化数据」，不依赖任何 GUI 库，便于单独测试。
"""

from __future__ import annotations

import re
from pathlib import Path

# --------------------------------------------------------------------------
# 基础解析
# --------------------------------------------------------------------------

_FLOAT_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _to_float(text):
    """从任意字符串中取出最后一个浮点数，失败返回 None。"""
    if text is None:
        return None
    matches = _FLOAT_RE.findall(str(text))
    if not matches:
        return None
    try:
        return float(matches[-1])
    except ValueError:
        return None


def parse_planar_average(path):
    """解析 vaspkit 426 的 ``PLANAR_AVERAGE.dat``。

    文件为两列（或多列，取后两列）：``z(Å)`` 与 ``平面平均势(eV)``。
    返回 ``(xs, vs, skipped)``，其中 ``skipped`` 为被忽略的行数。
    """
    xs, vs = [], []
    skipped = 0
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise FileNotFoundError(f"无法读取 {path}：{exc}") from exc
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        parts = line.split()
        if len(parts) < 2:
            skipped += 1
            continue
        try:
            x = float(parts[-2])
            v = float(parts[-1])
        except ValueError:
            skipped += 1
            continue
        xs.append(x)
        vs.append(v)
    if len(xs) < 10:
        raise ValueError(f"PLANAR_AVERAGE.dat 的有效数据点不足（仅 {len(xs)} 个）")
    return xs, vs, skipped


def parse_efermi_text(text):
    """从文本（cmd.log / OUTCAR / vasprun.xml）检索费米能级。"""
    if not text:
        return None
    # OUTCAR / cmd.log: "E-fermi :  -1.5600 ..."
    m = re.search(r"E-fermi\s*[:=]\s*([-+]?\d+\.\d+)", text)
    if m:
        return float(m.group(1))
    # vasprun.xml: <i name="efermi">  -1.5599903881 </i>
    m = re.search(r'name="efermi"[^>]*>\s*([-+]?\d+\.\d+)', text)
    if m:
        return float(m.group(1))
    return None


def parse_cmd_log_text(text):
    """从 vaspkit ``cmd.log`` 检索 E_F / 真空能级 / 功函数。"""
    out = {"efermi": None, "vacuum": None, "work_function": None}
    if not text:
        return out
    for line in text.splitlines():
        if out["efermi"] is None:
            m = re.search(r"E-fermi\s*[:=]\s*([-+]?\d+\.\d+)", line)
            if m:
                out["efermi"] = float(m.group(1))
        if out["vacuum"] is None:
            m = re.search(
                r"[Vv]acuum[- ]?[Ll]evel\s*\(?\s*eV\s*\)?\s*[:=]?\s*"
                r"([-+]?\d+\.\d+)", line)
            if m:
                out["vacuum"] = float(m.group(1))
        if out["work_function"] is None:
            m = re.search(
                r"[Ww]ork\s+[Ff]unction\s*\(?\s*eV\s*\)?\s*[:=]?\s*"
                r"([-+]?\d+\.\d+)", line)
            if m:
                out["work_function"] = float(m.group(1))
    return out


def parse_efermi_file(path):
    """从单个文件（OUTCAR / vasprun.xml / cmd.log）读取费米能级。"""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return parse_efermi_text(text)


def parse_poscar(path):
    """解析 POSCAR / CONTCAR：晶格长度、元素与原子数、化学式。

    兼容 VASP4（第 6 行直接是原子数）与 VASP5（第 6 行是元素名，第 7 行是原子数）。
    """
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if len(lines) < 7:
        return None
    try:
        scale = float(lines[1].split()[0])
    except (ValueError, IndexError):
        scale = 1.0

    def vec(line):
        vals = [float(x) for x in line.split()[:3]]
        return [v * scale for v in vals]

    try:
        a = vec(lines[2])
        b = vec(lines[3])
        c = vec(lines[4])
    except (ValueError, IndexError):
        return None
    import math
    c_len = math.sqrt(sum(v * v for v in c))

    idx = 5
    tokens = lines[5].split()
    # VASP5：第 6 行是元素符号（非纯数字）
    if tokens and not all(re.fullmatch(r"[-+]?\d+", t) for t in tokens):
        elements = tokens
        idx = 6
    else:
        elements = []
    try:
        counts = [int(x) for x in lines[idx].split()]
    except (ValueError, IndexError):
        counts = []
    natoms = sum(counts) if counts else 0
    if not elements:
        elements = [f"El{i + 1}" for i in range(len(counts))]
    formula = "".join(f"{e}{n}" for e, n in zip(elements, counts)) or "—"
    return {
        "c_length": c_len,
        "lattice": [a, b, c],
        "elements": elements,
        "counts": counts,
        "natoms": natoms,
        "formula": formula,
    }


# --------------------------------------------------------------------------
# 目录级装载
# --------------------------------------------------------------------------

PLANAR_NAMES = ("PLANAR_AVERAGE.dat", "PLANAR_AVERAGE.DAT",
                "planar_average.dat")


def _find_file(root, names):
    root = Path(root)
    for nm in names:
        p = root / nm
        if p.is_file():
            return p
    # 大小写不敏感兜底
    lowered = {n.lower() for n in names}
    try:
        for p in root.iterdir():
            if p.is_file() and p.name.lower() in lowered:
                return p
    except OSError:
        pass
    return None


def _compute_vacuum(vs):
    """兜底：真空能级取两端平台中势能较高的一侧（各取 1/10，至少 5 点平均）。"""
    n = len(vs)
    k = max(n // 10, 5)
    left = sum(vs[:k]) / k
    right = sum(vs[-k:]) / k
    return max(left, right)


def load_workfunction(source, planar_path=None):
    """从作业目录（或直接指向 PLANAR_AVERAGE.dat）装载功函数数据。

    参数
    ----
    source : str | Path
        作业目录，或 ``PLANAR_AVERAGE.dat`` 文件本身。
    planar_path : str | Path | None
        显式指定平面平均文件（source 为目录时可选，默认自动查找）。

    返回
    ----
    dict，包含：
        z, potential            平面平均势曲线
        efermi, v_vacuum, work_function
        wf_source               'cmd.log' | 'computed'
        c_length, atom_count, formula, elements
        files                   {name: Path 或 None}
        skipped                 被忽略的无效行数
    """
    src = Path(source)
    if src.is_file():
        planar = src
        root = src.parent
    else:
        root = src
        planar = Path(planar_path) if planar_path else _find_file(root, PLANAR_NAMES)
    if planar is None or not Path(planar).is_file():
        raise FileNotFoundError(
            f"未在 {root} 找到 PLANAR_AVERAGE.dat（请确认已完成 vaspkit 426）")

    xs, vs, skipped = parse_planar_average(planar)

    files = {
        "planar": Path(planar),
        "cmd.log": _find_file(root, ("cmd.log", "CMD.LOG")),
        "OUTCAR": _find_file(root, ("OUTCAR", "outcar")),
        "vasprun.xml": _find_file(root, ("vasprun.xml",)),
        "POSCAR": _find_file(root, ("POSCAR", "CONTCAR")),
        "LOCPOT": _find_file(root, ("LOCPOT",)),
    }

    # ---- 1) 优先从 cmd.log 检索 ----
    cmd = {"efermi": None, "vacuum": None, "work_function": None}
    if files["cmd.log"]:
        cmd = parse_cmd_log_text(
            Path(files["cmd.log"]).read_text(encoding="utf-8", errors="replace"))

    efermi = cmd["efermi"]
    if efermi is None:
        for key in ("OUTCAR", "vasprun.xml"):
            if files[key]:
                efermi = parse_efermi_file(files[key])
                if efermi is not None:
                    break

    wf_source = "cmd.log"
    if cmd["vacuum"] is not None and cmd["work_function"] is not None:
        vvac = cmd["vacuum"]
        wf = cmd["work_function"]
    else:
        if efermi is None:
            raise ValueError(
                "无法从 cmd.log / OUTCAR / vasprun.xml 提取费米能级 E_F，"
                "请确认作业已正常完成")
        vvac = _compute_vacuum(vs)
        wf = vvac - efermi
        wf_source = "computed"

    # ---- 2) 结构信息 ----
    struct = parse_poscar(files["POSCAR"]) if files["POSCAR"] else None
    c_len = (struct or {}).get("c_length") or (max(xs) if xs else None)

    return {
        "z": xs,
        "potential": vs,
        "efermi": efermi,
        "v_vacuum": vvac,
        "work_function": wf,
        "wf_source": wf_source,
        "c_length": c_len,
        "atom_count": (struct or {}).get("natoms"),
        "formula": (struct or {}).get("formula"),
        "elements": (struct or {}).get("elements", []),
        "files": files,
        "skipped": skipped,
        "root": root,
    }


def is_workfunction_dir(path):
    """快速判断目录是否像一份功函数输出。"""
    try:
        root = Path(path)
        if not root.is_dir():
            return False
        return _find_file(root, PLANAR_NAMES) is not None
    except OSError:
        return False


def data_to_csv(data):
    """把结果整理成 CSV 文本（与 Web_Probe 下载接口一致）。"""
    lines = ["z (Angstrom),planar average potential (eV)"]
    for x, v in zip(data["z"], data["potential"]):
        lines.append(f"{x:.6f},{v:.6f}")
    lines.append("")
    lines.append(f"E_F (eV),{data['efermi']:.6f}")
    lines.append(f"V_vacuum (eV),{data['v_vacuum']:.6f}")
    lines.append(f"work function (eV),{data['work_function']:.6f}")
    return "\n".join(lines)


if __name__ == "__main__":  # 简易自测
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    d = load_workfunction(target)
    print(f"数据点      : {len(d['z'])}")
    print(f"E_F         : {d['efermi']:.4f} eV")
    print(f"V_vac       : {d['v_vacuum']:.4f} eV")
    print(f"功函数 Φ    : {d['work_function']:.4f} eV")
    print(f"来源        : {d['wf_source']}")
    print(f"晶格 c      : {d['c_length']}")
    print(f"体系        : {d['formula']}（{d['atom_count']} 原子）")
