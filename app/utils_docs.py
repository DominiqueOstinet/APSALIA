# app/utils_docs.py
import os
import io
import tempfile

try:
    from docx import Document
    DOCX_AVAILABLE = True
except Exception:
    DOCX_AVAILABLE = False

try:
    import pypdf
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False


def extract_document_content(uploaded_file) -> str:
    """
    Extrait le contenu textuel d'un fichier uploadé (TXT, DOCX/DOC, PDF).
    Retourne une chaîne avec messages d’erreur en cas de problème.
    """
    file_extension = uploaded_file.name.lower().split('.')[-1]
    file_content = ""

    try:
        if file_extension == "txt":
            file_content = str(uploaded_file.read(), "utf-8")

        elif file_extension in ["docx", "doc"]:
            if not DOCX_AVAILABLE:
                return "[Erreur: Bibliothèque python-docx non installée. pip install python-docx]"
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name
            try:
                doc = Document(tmp_path)
                paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
                file_content = "\n\n".join(paragraphs) if paragraphs else "[Document DOCX vide]"
            except Exception as e:
                file_content = f"[Erreur extraction DOCX: {e}]"
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        elif file_extension == "pdf":
            if not PDF_AVAILABLE:
                return "[Erreur: Bibliothèque PyPDF non installée]"
            try:
                reader = pypdf.PdfReader(io.BytesIO(uploaded_file.getvalue()))
                pages = []
                for i, page in enumerate(reader.pages):
                    try:
                        text = page.extract_text() or ""
                        text = text.strip()
                        if text:
                            pages.append(f"[Page {i+1}]\n{text}")
                    except Exception as e:
                        pages.append(f"[Erreur page {i+1}: {e}]")
                file_content = "\n\n".join(pages) if pages else "[PDF vide ou non extractible]"
            except Exception as e:
                file_content = f"[Erreur extraction PDF: {e}]"

        else:
            file_content = f"[Format non supporté: .{file_extension}]"

    except Exception as e:
        file_content = f"[Erreur générale pour {uploaded_file.name}: {e}]"

    return file_content
