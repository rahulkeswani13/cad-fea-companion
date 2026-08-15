# Companion post-open helper for FreeCAD GUI.
# Makes FEM/CAD objects visible, expands analysis content, fits isometric view.
#
# Invoked as: FreeCAD document.FCStd companion/macros/show_fit.py

from __future__ import annotations


def _show_object(obj) -> None:
    try:
        if hasattr(obj, "Visibility"):
            obj.Visibility = True
    except Exception:
        pass
    try:
        vo = getattr(obj, "ViewObject", None)
        if vo is None:
            return
        if hasattr(vo, "Visibility"):
            vo.Visibility = True
        if hasattr(vo, "ShowInTree"):
            vo.ShowInTree = True
        if hasattr(vo, "HideInTree"):
            vo.HideInTree = False
        # Prefer shaded surface for meshes / result pipelines.
        modes = []
        try:
            modes = list(vo.listDisplayModes())
        except Exception:
            modes = []
        for preferred in ("Surface", "Flat Lines", "Shaded", "Wireframe"):
            if preferred in modes:
                try:
                    vo.DisplayMode = preferred
                    break
                except Exception:
                    pass
        # Color by von Mises when the VTK pipeline exposes it.
        for attr, value in (
            ("Field", "von Mises Stress"),
            ("Field", "vonMises"),
            ("DisplayModeField", "von Mises Stress"),
        ):
            if hasattr(vo, attr):
                try:
                    setattr(vo, attr, value)
                    break
                except Exception:
                    pass
    except Exception:
        pass


def _expand_model_tree() -> None:
    import FreeCADGui as Gui

    try:
        from PySide import QtWidgets  # type: ignore
    except Exception:
        try:
            from PySide2 import QtWidgets  # type: ignore
        except Exception:
            try:
                from PySide6 import QtWidgets  # type: ignore
            except Exception:
                return

    mw = Gui.getMainWindow()
    if mw is None:
        return
    for cls_name in ("QTreeWidget", "QTreeView"):
        cls = getattr(QtWidgets, cls_name, None)
        if cls is None:
            continue
        for widget in mw.findChildren(cls):
            try:
                widget.expandAll()
            except Exception:
                pass


def _fit_isometric() -> None:
    import FreeCADGui as Gui

    try:
        Gui.activateWorkbench("FemWorkbench")
    except Exception:
        try:
            Gui.activateWorkbench("PartWorkbench")
        except Exception:
            pass

    _expand_model_tree()

    view = None
    try:
        view = Gui.activeDocument().activeView()
    except Exception:
        view = None

    if view is not None:
        for name in ("viewIsometric", "viewAxonometric"):
            fn = getattr(view, name, None)
            if callable(fn):
                try:
                    fn()
                    break
                except Exception:
                    pass

    try:
        Gui.SendMsgToActiveView("ViewFit")
    except Exception:
        pass
    if view is not None:
        try:
            view.fitAll()
        except Exception:
            pass


def show_fit() -> None:
    import FreeCAD as App
    import FreeCADGui as Gui

    doc = App.ActiveDocument
    if doc is None:
        docs = list(App.listDocuments().values())
        doc = docs[-1] if docs else None
    if doc is None:
        return

    Gui.ActiveDocument = Gui.getDocument(doc.Name)

    # Unhide everything, including Analysis children / result pipelines.
    for obj in doc.Objects:
        _show_object(obj)

    # Keep the colored result pipeline on top when present.
    for name in (
        "Pipeline_CCX_Results",
        "CCX_Results",
        "FEMMeshGmsh",
        "Mount",
        "EngineMountBracket",
        "Beam",
        "CantileverBeam",
    ):
        obj = doc.getObject(name)
        if obj is not None:
            _show_object(obj)

    doc.recompute()
    _fit_isometric()


def _schedule() -> None:
    # Wait until the 3D view finishes loading the document.
    try:
        from PySide import QtCore  # type: ignore
    except Exception:
        try:
            from PySide2 import QtCore  # type: ignore
        except Exception:
            try:
                from PySide6 import QtCore  # type: ignore
            except Exception:
                show_fit()
                return

    QtCore.QTimer.singleShot(400, show_fit)
    QtCore.QTimer.singleShot(1200, show_fit)


_schedule()
