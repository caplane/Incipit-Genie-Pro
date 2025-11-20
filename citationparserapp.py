#!/usr/bin/env python3
"""
Incipit Genie Pro v3.3 - Final Production Edition
Features:
1. Preview Mode: Audit changes before processing
2. Expanded Journal Database: 20+ Psychiatric specific journals
3. Enhanced Parsers: 'Et al.' support, Arbitration/Personal Archive patterns
4. CMS 17th Ed: Ibid, Short Notes, Author Reordering
5. Railway deployment optimized
"""

from flask import Flask, render_template, request, send_file, flash, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import shutil
import zipfile
import xml.etree.ElementTree as ET
import re
import traceback
import logging
import time
import uuid
from pathlib import Path
from functools import lru_cache
from datetime import datetime, timedelta
import atexit
import tempfile

# Setup Logging for production
log_level = logging.DEBUG if os.environ.get('FLASK_ENV') == 'development' else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24).hex())

# Add proxy fix for Railway deployment
if os.environ.get('FLASK_ENV') == 'production':
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_CONTENT_LENGTH', 100 * 1024 * 1024))

# Create temp upload directory - use system temp for Railway
if os.environ.get('RAILWAY_ENVIRONMENT'):
    app.config['UPLOAD_FOLDER'] = os.path.join(tempfile.gettempdir(), 'incipit_uploads')
else:
    app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'temp_uploads')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Cleanup old files function
def cleanup_old_files():
    """Remove files older than 1 hour"""
    try:
        cutoff = datetime.now() - timedelta(hours=1)
        upload_path = Path(app.config['UPLOAD_FOLDER'])
        if upload_path.exists():
            for file in upload_path.iterdir():
                if file.is_file():
                    file_time = datetime.fromtimestamp(file.stat().st_mtime)
                    if file_time < cutoff:
                        try:
                            file.unlink()
                            logger.info(f"Cleaned up old file: {file.name}")
                        except Exception as e:
                            logger.error(f"Failed to cleanup {file.name}: {e}")
    except Exception as e:
        logger.error(f"Cleanup task failed: {e}")

# Register cleanup on exit
atexit.register(cleanup_old_files)
# Run initial cleanup
cleanup_old_files()

ALLOWED_EXTENSIONS = {'docx'}

NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'xml': 'http://www.w3.org/XML/1998/namespace'
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def qn(tag):
    prefix, tag_name = tag.split(':')
    return f"{{{NS[prefix]}}}{tag_name}"

def safe_extract(zip_ref, extract_path):
    extract_path = Path(extract_path).resolve()
    for member in zip_ref.infolist():
        member_path = (extract_path / member.filename).resolve()
        if extract_path not in member_path.parents and extract_path != member_path:
            raise ValueError(f"Malicious file path detected: {member.filename}")
        zip_ref.extract(member, extract_path)

# --- CLASS: Citation Manager ---
class CitationManager:
    def __init__(self):
        self.history = [] 
        self.seen_works = {} 
        
        # Extended Psychiatric Journal Database
        self.med_journals = [
            'Am J Psychiatry', 'American Journal of Psychiatry',
            'JAMA', 'NEJM', 'New England Journal of Medicine',
            'Arch Gen Psychiatry', 'Archives of General Psychiatry',
            'Lancet', 'BMJ', 'British Medical Journal',
            'Psychiatric Services', 'J Clin Psychiatry', 'Journal of Clinical Psychiatry',
            'Biological Psychiatry', 'Psychological Medicine',
            'Hospital and Community Psychiatry', 'Bulletin of the Menninger Clinic',
            'J Nerv Ment Dis', 'Journal of Nervous and Mental Disease'
        ]

    @lru_cache(maxsize=512)
    def generate_fingerprint(self, author, title):
        """Creates a normalized ID (Cached)."""
        if not title: return None
        auth_str = re.sub(r'\W+', '', author).lower() if author else "no_auth"
        title_str = re.sub(r'\W+', '', title).lower()[:25]
        return f"{auth_str}_{title_str}"

    def clean_text_formatting(self, text):
        """Fixes dashes, removes p./pp., normalizes spaces."""
        text = re.sub(r'(?<=[\s(,])p{1,2}\.\s*(?=\d)', '', text)
        text = re.sub(r'(\d)-(\d)', r'\1\u2013\2', text) # En-dash
        return text.strip()

    def get_short_title(self, full_title):
        """Intelligent short title generation."""
        if not full_title: return ""
        
        # 1. Strip Subtitles
        if ':' in full_title:
            short = full_title.split(':')[0]
        else:
            short = full_title

        # 2. Strip leading articles
        short = re.sub(r'^(The|A|An)\s+', '', short)

        # 3. Truncate if still too long
        words = short.split()
        if len(words) > 5:
            return ' '.join(words[:5])
        return short

    # --- PARSING LOGIC ---

    def parse_archival(self, text):
        """Enhanced for Osheroff/Psychiatric Archives"""
        patterns = [
            r'(.+?)\s*,\s*(Box|Folder|Tape|Reel|Carton)\s+(\d+)',
            r'(.+?)\s+Arbitration\s+(Videos?|Tapes?|Transcripts?)(?:,\s*(.+))?',
            r'(.+?)\s+Papers\s*,\s*(.+)',
            r'(.+?)\s+Archives?\s*,\s*(.+)',
            r'(.+?)\s+Collection\s*,\s*(.+)',
            r'(.+?)\s+Personal\s+Archive(?:,\s*(.+))?'
        ]
        for p in patterns:
            match = re.match(p, text, re.IGNORECASE)
            if match:
                # If it's the Arbitration Videos specific case
                if "Arbitration" in text:
                    return {
                        'type': 'archival',
                        'author': None,
                        'title': match.group(0).split(',')[0], # "Osheroff Arbitration Videos"
                        'details': text
                    }
                
                return {
                    'type': 'archival',
                    'author': None,
                    'title': match.group(1).strip(), 
                    'details': match.group(0)
                }
        return None

    def parse_transcript(self, text):
        """Handle: Klerman Deposition, Oct 15, 1985"""
        if 'Deposition' in text or 'Testimony' in text or 'Transcript' in text:
            parts = text.split(',')
            return {
                'type': 'transcript',
                'author': parts[0].strip(), 
                'title': parts[0].strip(),  
                'pub': parts[1].strip() if len(parts) > 1 else None
            }
        return None

    def parse_medical(self, text):
        """Handle: Author. Title. Am J Psychiatry..."""
        for journal in self.med_journals:
            if journal in text:
                try:
                    pre_j, post_j = text.split(journal, 1)
                    
                    # Pre-Journal contains Author. Title.
                    parts = re.split(r'\.\s+(?=[A-Z"\'\u201c])', pre_j.strip(), 1)
                    
                    author = parts[0].strip() if len(parts) > 0 else None
                    title = parts[1].strip(' .') if len(parts) > 1 else "Title Unknown"
                    
                    # Clean Author
                    if author:
                        # Handle "et al."
                        author = re.sub(r'\bet\s+al\.?', 'et al.', author, flags=re.IGNORECASE)
                        
                        # Reorder Last, First -> First Last (if not et al)
                        if ',' in author and 'et al.' not in author:
                            last, first = author.split(',', 1)
                            author = f"{first.strip()} {last.strip()}"

                    return {
                        'type': 'medical',
                        'author': author,
                        'title': title,
                        'pub': f"{journal} {post_j.strip()}"
                    }
                except:
                    continue 
        return None

    def parse_citation(self, text):
        """Master Parser: Waterfall logic"""
        data = {'raw': text, 'author': None, 'title': None, 'pub': None, 'page': None, 'type': 'generic'}
        
        text = self.clean_text_formatting(text)

        # 1. Extract Page Number
        page_match = re.search(r'[,.]\s*(\d+[-\u2013]?\d*)\.?$', text)
        if page_match:
            data['page'] = page_match.group(1)
            text = text[:page_match.start()].strip().rstrip('.,')

        # 2. Check Specialized Formats
        arch = self.parse_archival(text)
        if arch: 
            arch['page'] = data['page']
            return arch
        
        trans = self.parse_transcript(text)
        if trans:
            trans['page'] = data['page']
            return trans

        # Legal (" v. ")
        if re.search(r'\s+v\.\s+', text):
            return {'type': 'legal', 'title': text, 'page': data['page'], 'author': None}

        med = self.parse_medical(text)
        if med:
            med['page'] = data['page']
            return med

        # Books (City: Pub)
        pub_pattern = r'\(?([A-Za-z\s\.]+:\s*[^,()]+,\s*\d{4})\)?'
        pub_match = re.search(pub_pattern, text)

        if pub_match:
            data['type'] = 'book'
            data['pub'] = pub_match.group(1)
            pre_pub = text[:pub_match.start()].strip().rstrip('.,')

            # Author/Title Split
            author_pattern = r'^([A-Z][\w\-\']+(?:,\s+(?:Jr\.|Sr\.|III))?,\s+[A-Z][\w\-\'\.]+(?:\s+[A-Z]\.)?)'
            auth_match = re.match(author_pattern, pre_pub)

            if auth_match:
                raw_author = auth_match.group(1)
                data['title'] = pre_pub[auth_match.end():].strip('., ')
                parts = raw_author.split(',', 1)
                data['author'] = f"{parts[1].strip()} {parts[0].strip()}" if len(parts) == 2 else raw_author
            else:
                parts = re.split(r'\.\s+(?=[A-Z"\'\u201c])', pre_pub, 1)
                if len(parts) > 1:
                    data['author'] = parts[0].strip()
                    data['title'] = parts[1].strip()
                else:
                    data['title'] = pre_pub
            return data

        # Fallback (Journal/Generic)
        parts = re.split(r'\.\s+(?=[A-Z"\'\u201c])', text, 1)
        if len(parts) > 1 and ',' in parts[0]:
            name_parts = parts[0].split(',', 1)
            data['author'] = f"{name_parts[1].strip()} {name_parts[0].strip()}"
            data['title'] = parts[1]
            data['type'] = 'journal'
        else:
            data['title'] = text
            
        return data

    def process(self, raw_text):
        parsed = self.parse_citation(raw_text)
        
        if not parsed['title'] and not parsed['author']:
            return self.clean_text_formatting(raw_text)

        fingerprint = self.generate_fingerprint(parsed['author'], parsed['title'])
        final_str = ""
        
        # A. IBID
        if self.history and self.history[-1].get('fingerprint') == fingerprint:
            final_str = "Ibid."
            if parsed['page']: final_str += f", {parsed['page']}"

        # B. SHORT NOTE
        elif fingerprint in self.seen_works:
            prev_data = self.seen_works[fingerprint]
            
            if parsed['type'] == 'legal':
                final_str = parsed['title'].split(',')[0] 
            elif parsed['type'] == 'archival':
                final_str = parsed['title'] 
            elif parsed['type'] == 'transcript':
                final_str = parsed['title']
            else:
                short_title = self.get_short_title(prev_data['title'])
                if parsed['author']:
                    final_str = f"{parsed['author']}, {short_title}"
                else:
                    final_str = short_title
            
            if parsed['page']: final_str += f", {parsed['page']}"

        # C. FULL NOTE
        else:
            self.seen_works[fingerprint] = parsed
            
            if parsed['type'] == 'legal':
                final_str = parsed['title']
            elif parsed['type'] == 'archival':
                final_str = f"{parsed['title']}, {parsed.get('details', '')}"
            elif parsed['type'] == 'book' and parsed['pub']:
                auth_str = f"{parsed['author']}, " if parsed['author'] else ""
                final_str = f"{auth_str}{parsed['title']} ({parsed['pub']})"
            else:
                auth_str = f"{parsed['author']}, " if parsed['author'] else ""
                final_str = f"{auth_str}{parsed['title']}"
                if parsed['type'] == 'medical':
                    final_str += f" {parsed.get('pub', '')}"

            if parsed['page']: final_str += f", {parsed['page']}"

        parsed['fingerprint'] = fingerprint
        self.history.append(parsed)
        return final_str

# --- CLASS: Incipit Extractor (Unchanged) ---
class IncipitExtractor:
    def __init__(self, word_count=3):
        self.word_count = word_count
    
    def get_sentence_start(self, text, position):
        text_before = text[:position]
        if not text_before: return ""
        pattern = (
            r'(?<!Dr)(?<!Mr)(?<!Ms)(?<!Mrs)(?<!Prof)(?<!Rev)(?<!Sen)(?<!Rep)(?<!v)' 
            r'(?<=[.?!])\s+(?=[A-Z])' 
        )
        sentences = re.split(pattern, text_before)
        if not sentences: return ""
        current_sentence = sentences[-1].strip()
        current_sentence = re.sub(r'^["\'\u201c\u2018\s]+', '', current_sentence)
        words = current_sentence.split()
        selected_words = words[:self.word_count]
        if selected_words:
            selected_words[-1] = re.sub(r'[.,;:!?"\'\u201d\u2019]+$', '', selected_words[-1])
        return ' '.join(selected_words)

    def extract_contexts(self, doc_tree):
        contexts = {}
        for p in doc_tree.iter(qn('w:p')):
            runs_data = [] 
            for child in p:
                if child.tag == qn('w:r'):
                    t_elem = child.find(qn('w:t'))
                    text_content = t_elem.text if (t_elem is not None and t_elem.text) else ""
                    ref = child.find(qn('w:endnoteReference'))
                    e_id = ref.get(qn('w:id')) if ref is not None else None
                    runs_data.append({'text': text_content, 'id': e_id})
            
            current_pos = 0
            full_para_text = "".join([r['text'] for r in runs_data])
            
            for run in runs_data:
                current_pos += len(run['text'])
                if run['id']:
                    contexts[run['id']] = self.get_sentence_start(full_para_text, current_pos)
        return contexts

# --- Processing Logic ---
def process_document_xml(doc_tree, endnotes_tree, contexts, format_bold=True, apply_cms=True):
    ref_map = {}
    def id_generator():
        count = 10000
        while True:
            yield str(count)
            count += 1
    bm_id_gen = id_generator()
    
    refs_to_process = []
    for p in doc_tree.iter(qn('w:p')):
        for r in p.findall(qn('w:r')):
            ref = r.find(qn('w:endnoteReference'))
            if ref is not None: refs_to_process.append((p, r, ref))

    for parent_p, run, ref in refs_to_process:
        e_id = ref.get(qn('w:id'))
        if e_id in ['0', '-1']: continue

        b_name = f"REF_NOTE_{e_id}"
        b_id = next(bm_id_gen)
        ref_map[e_id] = b_name
        
        bm_start = ET.Element(qn('w:bookmarkStart'), {qn('w:id'): b_id, qn('w:name'): b_name})
        bm_end = ET.Element(qn('w:bookmarkEnd'), {qn('w:id'): b_id})
        
        p_children = list(parent_p)
        try:
            r_index = p_children.index(run)
            parent_p.insert(r_index, bm_start)
            parent_p.insert(r_index + 2, bm_end)
        except ValueError: continue
        
        run.remove(ref)
        t = run.find(qn('w:t'))
        if t is not None: run.remove(t)

    cit_manager = CitationManager() if apply_cms else None
    notes_container = []
    
    header_p = ET.Element(qn('w:p'))
    pPr = ET.SubElement(header_p, qn('w:pPr'))
    ET.SubElement(pPr, qn('w:pStyle'), {qn('w:val'): 'Heading1'})
    ET.SubElement(ET.SubElement(header_p, qn('w:r')), qn('w:t')).text = "Notes"
    notes_container.append(header_p)
    
    sorted_ids = sorted([eid for eid in ref_map.keys()], key=lambda x: int(x) if x.isdigit() else 0)
    endnotes_map = {e.get(qn('w:id')): e for e in endnotes_tree.findall(qn('w:endnote'))}

    for e_id in sorted_ids:
        original_note = endnotes_map.get(e_id)
        if original_note is None: continue
            
        note_p = ET.Element(qn('w:p'))
        pPr = ET.SubElement(note_p, qn('w:pPr'))
        ET.SubElement(pPr, qn('w:spacing'), {qn('w:after'): '240'}) 
        
        b_name = ref_map[e_id]
        fldSimple = ET.SubElement(note_p, qn('w:fldSimple'), {qn('w:instr'): f" PAGEREF {b_name} \\h "})
        ET.SubElement(ET.SubElement(fldSimple, qn('w:r')), qn('w:t')).text = "0"
        ET.SubElement(ET.SubElement(note_p, qn('w:r')), qn('w:t'), {qn('xml:space'): 'preserve'}).text = ". "
        
        incipit = contexts.get(e_id)
        if incipit:
            r_inc = ET.SubElement(note_p, qn('w:r'))
            rPr = ET.SubElement(r_inc, qn('w:rPr'))
            if format_bold: ET.SubElement(rPr, qn('w:b'))
            else: ET.SubElement(rPr, qn('w:i'))
            ET.SubElement(r_inc, qn('w:t')).text = f"{incipit}"
            ET.SubElement(ET.SubElement(note_p, qn('w:r')), qn('w:t'), {qn('xml:space'): 'preserve'}).text = ": "

        if apply_cms:
            full_text_list = []
            for p in original_note.findall(qn('w:p')):
                for r in p.findall(qn('w:r')):
                    if r.find(qn('w:endnoteRef')) is not None: continue
                    for t in r.findall(qn('w:t')):
                        if t.text: full_text_list.append(t.text)
            
            raw_text = "".join(full_text_list)
            try:
                processed_text = cit_manager.process(raw_text)
                new_r = ET.SubElement(note_p, qn('w:r'))
                ET.SubElement(new_r, qn('w:t')).text = processed_text
            except:
                 for child_p in original_note.findall(qn('w:p')):
                    for child_r in child_p.findall(qn('w:r')):
                        if child_r.find(qn('w:endnoteRef')) is None: note_p.append(child_r)
        else:
            for child_p in original_note.findall(qn('w:p')):
                for child_r in child_p.findall(qn('w:r')):
                    if child_r.find(qn('w:endnoteRef')) is None: note_p.append(child_r)
        
        notes_container.append(note_p)

    body = doc_tree.find(qn('w:body'))
    if body is None: return 0
    br_p = ET.Element(qn('w:p'))
    ET.SubElement(ET.SubElement(br_p, qn('w:r')), qn('w:br'), {qn('w:type'): 'page'})
    body.append(br_p)
    for p in notes_container: body.append(p)
    return len(sorted_ids)

def convert_docx(input_path, output_path, word_count=3, format_bold=True, apply_cms=True):
    temp_dir = Path(app.config['UPLOAD_FOLDER']) / f"proc_{uuid.uuid4().hex}"
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        with zipfile.ZipFile(input_path, 'r') as z: safe_extract(z, temp_dir)
        doc_tree = ET.parse(str(temp_dir / 'word' / 'document.xml'))
        endnotes_tree = ET.parse(str(temp_dir / 'word' / 'endnotes.xml'))
        
        extractor = IncipitExtractor(word_count)
        contexts = extractor.extract_contexts(doc_tree)
        count = process_document_xml(doc_tree, endnotes_tree, contexts, format_bold, apply_cms)
        
        doc_tree.write(str(temp_dir / 'word' / 'document.xml'), encoding='UTF-8', xml_declaration=True)
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as z:
            for file_path in temp_dir.rglob('*'):
                if file_path.is_file(): z.write(file_path, file_path.relative_to(temp_dir))
        return True, f"Converted {count} notes"
    except Exception as e:
        logger.error(traceback.format_exc())
        return False, str(e)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/preview', methods=['POST'])
def preview():
    """Analyzes document and returns JSON of changes without saving"""
    if 'file' not in request.files: return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    
    temp_dir = Path(app.config['UPLOAD_FOLDER']) / f"preview_{uuid.uuid4().hex}"
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        filename = secure_filename(file.filename)
        input_path = temp_dir / filename
        file.save(input_path)
        
        with zipfile.ZipFile(input_path, 'r') as z: safe_extract(z, temp_dir)
        endnotes_tree = ET.parse(str(temp_dir / 'word' / 'endnotes.xml'))
        
        cm = CitationManager()
        changes = []
        
        # Iterate all endnotes
        for note in endnotes_tree.findall(qn('w:endnote')):
            e_id = note.get(qn('w:id'))
            if e_id in ['0', '-1']: continue
            
            full_text = []
            for p in note.findall(qn('w:p')):
                for r in p.findall(qn('w:r')):
                    for t in r.findall(qn('w:t')):
                        if t.text: full_text.append(t.text)
            
            raw = "".join(full_text)
            if not raw.strip(): continue
            
            processed = cm.process(raw)
            changes.append({
                'id': e_id,
                'raw': raw,
                'processed': processed,
                'type': cm.history[-1].get('type'),
                'fingerprint': cm.history[-1].get('fingerprint')
            })
            
        return jsonify(changes)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

@app.route('/convert', methods=['POST'])
def convert():
    if 'file' not in request.files: return redirect(url_for('index'))
    file = request.files['file']
    
    word_count = int(request.form.get('word_count', 3))
    format_style = request.form.get('format_style', 'bold') == 'bold'
    apply_cms = request.form.get('apply_cms', 'yes') == 'yes'

    filename = secure_filename(file.filename)
    unique_id = uuid.uuid4().hex[:8]
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{unique_id}_{filename}")
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"out_{unique_id}_{Path(filename).stem}_incipit.docx")

    try:
        file.save(input_path)
        success, msg = convert_docx(input_path, output_path, word_count, format_style, apply_cms)
        if success:
            response = send_file(output_path, as_attachment=True, download_name=f"{Path(filename).stem}_incipit.docx")
            @response.call_on_close
            def cleanup():
                try:
                    if os.path.exists(input_path): os.remove(input_path)
                    if os.path.exists(output_path): os.remove(output_path)
                except: pass
            return response
        else:
            flash(msg, 'error')
            return redirect(url_for('index'))
    except Exception:
        flash("System error", 'error')
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
