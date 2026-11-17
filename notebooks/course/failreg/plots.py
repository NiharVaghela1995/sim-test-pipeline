"""Small plotting helpers shared by the notebooks."""
import numpy as np
import matplotlib.pyplot as plt

BLUE, ORANGE, GREEN, GREY, RED = "#2a78d6", "#eb6834", "#2f9e57", "#8a8a8a", "#c8324b"
COLORS = [BLUE, ORANGE, GREEN, "#7b5cc4", GREY, RED, "#b58b00", "#1a9fb0"]


def style():
    plt.rcParams.update({"figure.dpi": 90, "axes.spines.top": False, "axes.spines.right": False, "font.size": 10})


def region_map(ax, problem, pred=None, X=None, title=None, Xfail=None):
    """True failure region (filled), predicted boundary (line), runs (dots; failing runs in red if Xfail given)."""
    G, truth, shape, ok = problem.test
    T = truth.reshape(shape).astype(float)
    if ok is not None:
        T = np.where(ok.reshape(shape), T, np.nan)
    ext = (0, 1, 0, 1)
    ax.imshow(T.T, origin="lower", extent=ext, cmap="Greys", vmin=-0.3, vmax=1.6, aspect="auto", interpolation="nearest")
    if pred is not None:
        P_ = np.asarray(pred, float).reshape(shape)
        g0, g1 = np.linspace(0, 1, shape[0]), np.linspace(0, 1, shape[1])
        ax.contour(g0, g1, P_.T, levels=[0.5], colors=[ORANGE], linewidths=1.5)
    if X is not None and len(X):
        ax.scatter(X[:, 0], X[:, 1], s=8, c=BLUE, lw=0)
    if Xfail is not None and len(Xfail):
        ax.scatter(Xfail[:, 0], Xfail[:, 1], s=10, c=RED, lw=0)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    if problem.labels:
        ax.set_xlabel(problem.labels[0]); ax.set_ylabel(problem.labels[1])
    ax.set_title(title or problem.name, loc="left")


def curves(ax, ns, arms, ylabel, logy=False):
    """arms: {name: array (seeds, len(ns))}. Median line and interquartile band."""
    for (name, A), c in zip(arms.items(), COLORS):
        A = np.asarray(A, float)
        ax.plot(ns, np.median(A, 0), color=c, label=name)
        ax.fill_between(ns, np.quantile(A, 0.25, 0), np.quantile(A, 0.75, 0), color=c, alpha=0.15, lw=0)
    ax.set_xlabel("runs"); ax.set_ylabel(ylabel)
    if logy:
        ax.set_yscale("symlog", linthresh=1e-3)
    ax.legend(frameon=False)
