#!/bin/bash
# ============================================================================
# cworkfunction.sh —— 功函数后处理脚本（在计算节点的作业目录中运行）
#
# 用途：
#   1) 调用 vaspkit 426（Potential Analysis）沿 c 方向做平面平均，
#      生成 PLANAR_AVERAGE.dat，并把 vaspkit 的输出写入 cmd.log；
#          426 = Potential Analysis
#          3   = Lattice c Direction
#   2) 追加 OUTCAR 中的费米能级（E-fermi）到 cmd.log。
#
#   生成的 cmd.log 含 Vacuum-Level / Work Function / E-fermi，
#   正是「WF · 功函数绘图工作台」读取的关键数值来源：
#          Φ = V_vacuum − E_Fermi
#
# 依赖：vaspkit（已加入 PATH）
#       作业目录下需有 LOCPOT / OUTCAR / POSCAR / DOSCAR
#
# 用法：
#   cd <作业目录> && bash cworkfunction.sh
# ============================================================================
echo -e "426\n3" | vaspkit > cmd.log
grep fermi OUTCAR | tail -1 >> cmd.log
