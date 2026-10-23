from __future__ import annotations
import argparse,hashlib,sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

SOURCES={
 "DTU-BTECH-ORD-2025":{"filename":"DTU_BTech_Ordinance_2025.pdf","extract":"DTU_BTech_Ordinance_2025.txt","ocr":"all"},
 "DTU-EXAM-ODD-2026-27":{"filename":"DTU_Exam_Eligibility_Odd_Sem_2026-27.pdf","extract":"DTU_Exam_Eligibility_Odd_Sem_2026-27.txt","ocr":"all"},
 "DTU-TNP-PLACEMENT-2025-26":{"filename":"DTU_Placement_Policy_2025-26.pdf","extract":"DTU_Placement_Policy_2025-26.txt","ocr":"missing"},
}

def ocr_pages(pdf_path:Path, page_numbers:list[int], workers:int=4)->dict[int,str]:
    try:
        import fitz
        from PIL import Image
        import pytesseract
    except Exception as exc:
        raise RuntimeError("OCR requires PyMuPDF, Pillow, pytesseract and the Tesseract executable.") from exc
    images={}
    with fitz.open(pdf_path) as doc:
        for n in page_numbers:
            page=doc[n-1]
            pix=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False)
            images[n]=Image.frombytes("RGB",[pix.width,pix.height],pix.samples)
    def one(item):
        n,img=item
        return n,pytesseract.image_to_string(img,config="--psm 6")
    with ThreadPoolExecutor(max_workers=max(1,workers)) as pool:
        return dict(pool.map(one,images.items()))

def extract(pdf_path:Path,out_path:Path,policy:str, start_page:int|None=None,end_page:int|None=None,workers:int=4)->None:
    try:
        import fitz
        from PIL import Image
        import pytesseract
    except Exception as exc:
        raise RuntimeError("PDF extraction requires PyMuPDF, Pillow, pytesseract and the Tesseract executable.") from exc
    with fitz.open(pdf_path) as doc:
        all_pages=len(doc)
        first=max(1,start_page or 1);last=min(all_pages,end_page or all_pages)
        out_path.parent.mkdir(parents=True,exist_ok=True)
        page_dir=out_path.with_suffix("").with_name(out_path.stem+"_pages")
        page_dir.mkdir(parents=True,exist_ok=True)
        needs_ocr=[];texts={}
        for n in range(first,last+1):
            page_file=page_dir/f"page-{n:04d}.txt"
            if page_file.exists() and page_file.stat().st_size>20:
                texts[n]=page_file.read_text(encoding="utf-8",errors="replace");continue
            body=doc[n-1].get_text("text").strip()
            if len(body)<25 and policy in {"all","missing"}:needs_ocr.append(n)
            else:texts[n]=body
        images={}
        for n in needs_ocr:
            pix=doc[n-1].get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False)
            images[n]=Image.frombytes("RGB",[pix.width,pix.height],pix.samples)
    if images:
        def one(item):
            n,img=item
            return n,pytesseract.image_to_string(img,config="--psm 6")
        with ThreadPoolExecutor(max_workers=max(1,workers)) as pool:
            texts.update({n:body.strip() for n,body in pool.map(one,images.items())})
    for n,body in texts.items():
        (page_dir/f"page-{n:04d}.txt").write_text(body,encoding="utf-8")
    if first==1 and last==all_pages:
        combined=[]
        for n in range(1,all_pages+1):
            page_file=page_dir/f"page-{n:04d}.txt"
            if page_file.exists():
                text=page_file.read_text(encoding="utf-8",errors="replace").strip()
                if text:combined.append(f"[PAGE {n}]\n{text}")
        body="\n\n".join(combined)
        if len(body)<100:raise ValueError(f"Extracted text appears unusable for {pdf_path.name}")
        out_path.write_text(body,encoding="utf-8")
        print(f"Extracted {pdf_path.name}: {all_pages} pages, {len(body):,} characters -> {out_path}")
    else:print(f"Processed pages {first}-{last} of {pdf_path.name}; page OCR checkpoints -> {page_dir}")

def main()->int:
    parser=argparse.ArgumentParser(description="Extract supplied official DTU policy PDFs with page anchors for RAG indexing")
    parser.add_argument("--source",choices=["all",*SOURCES.keys()],default="all")
    parser.add_argument("--start-page",type=int);parser.add_argument("--end-page",type=int)
    parser.add_argument("--workers",type=int,default=4);parser.add_argument("--extract-only",action="store_true",help="Only extract text; do not index ChromaDB")
    args=parser.parse_args(); official_dir=ROOT/"data"/"documents"/"official"; extract_dir=ROOT/"data"/"extracted"
    selected=SOURCES.items() if args.source=="all" else [(args.source,SOURCES[args.source])]
    try:
        for doc_id,spec in selected:
            src=official_dir/spec["filename"]
            if not src.exists():raise FileNotFoundError(f"Required supplied official PDF is missing: {src}")
            dst=extract_dir/spec["extract"]
            extract(src,dst,spec["ocr"],args.start_page,args.end_page,args.workers)
        if not args.extract_only and not args.start_page and not args.end_page:
            from app.db import init_db,seed_sources_and_rules
            init_db();seed_sources_and_rules()
            print("Official text is extracted and the starter source corpus has been indexed where RAG dependencies are available.")
        return 0
    except Exception as exc:
        print(f"OFFICIAL SOURCE INGESTION FAILED: {type(exc).__name__}: {exc}",file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())
