"""后台调用 Word 或 WPS（不显示窗口）：docx → PDF、doc → docx。

- 优先顺序由设置决定：auto（先 Word 后 WPS）/ word / wps；
- 兼容 Office 2013 及以上（ExportAsFixedFormat）；WPS 文字的 ProgID 为 KWPS.Application（旧版 WPS.Application）；
- 用户已打开 Word 时可能复用同一进程，所以只关闭自己打开的文档，进程里没有其他文档才退出。
"""
import os
import threading


PROGIDS = {"word": ["Word.Application"], "wps": ["KWPS.Application", "WPS.Application"]}
WD_EXPORT_PDF = 17          # wdExportFormatPDF / wdFormatPDF
WD_FORMAT_DOCX = 12         # wdFormatXMLDocument
_lock = threading.Lock()


class OfficeError(Exception):
    pass


def _candidates(engine: str):
    if engine in PROGIDS:
        return PROGIDS[engine]
    return PROGIDS["word"] + PROGIDS["wps"]


def available_engines() -> list:
    """检测本机可用的引擎（只查注册表，不启动程序）。"""
    if os.name != "nt":
        return []
    import winreg
    found = []
    for engine, ids in PROGIDS.items():
        for pid in ids:
            try:
                winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, pid + "\\CLSID"))
                found.append(engine)
                break
            except OSError:
                continue
    return found


def _open_app(engine: str):
    import comtypes.client

    errors = []
    for pid in _candidates(engine):
        try:
            app = comtypes.client.CreateObject(pid, dynamic=True)
        except Exception as e:      # 未安装或无法启动，换下一个
            errors.append(f"{pid}: {e}")
            continue
        try:
            app.Visible = False
            app.DisplayAlerts = 0
        except Exception:
            pass
        return app, pid
    raise OfficeError("没有找到可用的 Word 或 WPS：\n" + "\n".join(errors))


def _close_app(app):
    try:
        if app.Documents.Count == 0:
            app.Quit()
    except Exception:
        pass


def _run(engine, func):
    """在独立 COM 环境中执行 func(app)，可在后台线程调用。"""
    if os.name != "nt":
        raise OfficeError("后台 Office 转换需要 Windows 上的 Word 或 WPS。")
    import comtypes

    with _lock:
        comtypes.CoInitialize()
        try:
            app, pid = _open_app(engine)
            try:
                return func(app, pid)
            finally:
                _close_app(app)
        finally:
            comtypes.CoUninitialize()


def _open_doc(app, path):
    # FileName, ConfirmConversions, ReadOnly, AddToRecentFiles
    return app.Documents.Open(os.path.abspath(path), False, True, False)


def docx_to_pdf(docx_path, pdf_path, engine: str = "auto") -> str:
    def work(app, pid):
        doc = _open_doc(app, docx_path)
        try:
            try:
                doc.ExportAsFixedFormat(os.path.abspath(pdf_path), WD_EXPORT_PDF)
            except Exception:
                doc.SaveAs(os.path.abspath(pdf_path), WD_EXPORT_PDF)
        finally:
            doc.Close(False)
        return pid
    used = _run(engine, work)
    if not os.path.exists(pdf_path):
        raise OfficeError(f"{used} 未能生成 PDF：{pdf_path}")
    return used


def doc_to_docx(doc_path, docx_path, engine: str = "auto") -> str:
    def work(app, pid):
        doc = _open_doc(app, doc_path)
        try:
            doc.SaveAs(os.path.abspath(docx_path), WD_FORMAT_DOCX)
        finally:
            doc.Close(False)
        return pid
    return _run(engine, work)
