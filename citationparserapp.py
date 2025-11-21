#!/usr/bin/env python3
"""
Large File Optimization Fixes for Incipit Genie Pro v3.3
Addresses memory issues and performance bottlenecks
"""

import xml.etree.ElementTree as ET
from xml.etree.ElementTree import iterparse
import zipfile
import io
import gc
import logging

logger = logging.getLogger(__name__)

# FIX 1: Replace the Unicode bug (CRITICAL!)
def clean_text_formatting(self, text):
    """Fixed version without Unicode escape bug"""
    text = re.sub(r'(?<=[\s(,])p{1,2}\.\s*(?=\d)', '', text)
    text = re.sub(r'(\d)-(\d)', r'\1–\2', text)  # Use literal en-dash!
    return text.strip()


# FIX 2: Streaming XML parser for large documents
def process_large_document_streaming(doc_path, endnotes_path, word_count=3):
    """
    Stream-process large documents without loading entire XML into memory
    """
    contexts = {}
    endnotes = {}
    
    # Stream process document.xml for incipits
    logger.info("Streaming document.xml for incipits...")
    incipit_count = 0
    
    for event, elem in iterparse(doc_path, events=('start', 'end')):
        if event == 'end' and elem.tag.endswith('}p'):
            # Process paragraph
            text_parts = []
            endnote_refs = []
            
            for child in elem.iter():
                if child.tag.endswith('}t'):
                    if child.text:
                        text_parts.append(child.text)
                elif child.tag.endswith('}endnoteReference'):
                    e_id = child.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id')
                    if e_id:
                        endnote_refs.append((e_id, len(''.join(text_parts))))
            
            # Extract incipits for this paragraph
            if endnote_refs:
                full_text = ''.join(text_parts)
                for e_id, position in endnote_refs:
                    incipit = extract_incipit_at_position(full_text, position, word_count)
                    contexts[e_id] = incipit
                    incipit_count += 1
                    
                    if incipit_count % 50 == 0:
                        logger.info(f"Processed {incipit_count} incipits...")
            
            # Clear element to save memory
            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]
    
    # Stream process endnotes.xml
    logger.info("Streaming endnotes.xml...")
    endnote_count = 0
    
    for event, elem in iterparse(endnotes_path, events=('start', 'end')):
        if event == 'end' and elem.tag.endswith('}endnote'):
            e_id = elem.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id')
            
            if e_id and e_id not in ['0', '-1']:
                # Extract text from endnote
                text_parts = []
                for t_elem in elem.iter():
                    if t_elem.tag.endswith('}t'):
                        if t_elem.text:
                            text_parts.append(t_elem.text)
                
                endnotes[e_id] = ''.join(text_parts)
                endnote_count += 1
                
                if endnote_count % 50 == 0:
                    logger.info(f"Processed {endnote_count} endnotes...")
            
            # Clear element to save memory
            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]
    
    logger.info(f"Streaming complete: {incipit_count} incipits, {endnote_count} endnotes")
    return contexts, endnotes


# FIX 3: Chunked processing for very large files
def process_in_chunks(endnotes, chunk_size=100):
    """
    Process endnotes in chunks to avoid memory issues
    """
    from itertools import islice
    
    def chunk_dict(data, chunk_size):
        it = iter(data)
        while True:
            chunk = dict(islice(data.items(), chunk_size))
            if not chunk:
                break
            yield chunk
    
    processed_notes = {}
    cit_manager = CitationManager()
    
    for i, chunk in enumerate(chunk_dict(endnotes, chunk_size)):
        logger.info(f"Processing chunk {i+1} ({len(chunk)} notes)...")
        
        for note_id, note_text in chunk.items():
            try:
                processed = cit_manager.process(note_text)
                processed_notes[note_id] = processed
            except Exception as e:
                logger.warning(f"Failed to process note {note_id}: {e}")
                processed_notes[note_id] = note_text
        
        # Force garbage collection after each chunk
        gc.collect()
    
    return processed_notes


# FIX 4: Add file size check and warning
def check_file_size(file_path):
    """
    Check file size and warn for large files
    """
    import os
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    
    if size_mb > 50:
        logger.warning(f"Large file detected: {size_mb:.1f} MB")
        logger.info("Switching to streaming mode for better performance...")
        return True, size_mb
    
    return False, size_mb


# FIX 5: Progress callback for user feedback
class ProgressTracker:
    """
    Track processing progress for large files
    """
    def __init__(self, total_items):
        self.total = total_items
        self.current = 0
        self.last_percent = 0
    
    def update(self, increment=1):
        self.current += increment
        percent = int((self.current / self.total) * 100)
        
        if percent > self.last_percent and percent % 10 == 0:
            logger.info(f"Progress: {percent}% complete ({self.current}/{self.total})")
            self.last_percent = percent
    
    def complete(self):
        logger.info(f"Processing complete: {self.current} items processed")


# FIX 6: Optimized convert function for large files
def convert_docx_optimized(input_path, output_path, word_count=3, format_bold=True, apply_cms=True):
    """
    Optimized version that handles large files efficiently
    """
    import tempfile
    from pathlib import Path
    import shutil
    import uuid
    
    temp_dir = Path(tempfile.gettempdir()) / f"proc_{uuid.uuid4().hex}"
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        # Check file size
        is_large, size_mb = check_file_size(input_path)
        
        # Extract docx
        with zipfile.ZipFile(input_path, 'r') as z:
            z.extractall(temp_dir)
        
        doc_path = temp_dir / 'word' / 'document.xml'
        endnotes_path = temp_dir / 'word' / 'endnotes.xml'
        
        # Check for endnotes
        if not endnotes_path.exists():
            return False, "No endnotes found in this document."
        
        if is_large or size_mb > 10:
            # Use streaming for large files
            logger.info(f"Processing large file ({size_mb:.1f} MB) in streaming mode...")
            contexts, endnotes_text = process_large_document_streaming(
                doc_path, endnotes_path, word_count
            )
            
            # Process citations in chunks
            if apply_cms:
                processed_notes = process_in_chunks(endnotes_text, chunk_size=100)
            else:
                processed_notes = endnotes_text
            
            # Build output (simplified for large files)
            success = build_output_streaming(
                temp_dir, contexts, processed_notes, format_bold
            )
            
            if success:
                # Repack docx
                with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as z:
                    for file_path in temp_dir.rglob('*'):
                        if file_path.is_file():
                            z.write(file_path, file_path.relative_to(temp_dir))
                
                note_count = len(contexts)
                return True, f"Successfully converted {note_count} notes ({size_mb:.1f} MB file)"
            else:
                return False, "Failed to build output document"
        else:
            # Use original method for smaller files
            # ... (original convert_docx code for small files)
            pass
            
    except MemoryError:
        logger.error("Out of memory - file too large")
        return False, "File too large to process. Please split into smaller documents."
        
    except Exception as e:
        logger.error(f"Processing error: {e}")
        return False, str(e)
        
    finally:
        # Clean up
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        gc.collect()


# FIX 7: Add timeout and size limits to Flask route
from functools import wraps
import signal

def timeout(seconds):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            def timeout_handler(signum, frame):
                raise TimeoutError("Processing timeout - file too large")
            
            # Set timeout
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(seconds)
            
            try:
                result = func(*args, **kwargs)
            finally:
                signal.alarm(0)  # Cancel alarm
            
            return result
        return wrapper
    return decorator


@app.route('/convert', methods=['POST'])
@timeout(300)  # 5 minute timeout
def convert_with_timeout():
    """
    Convert route with timeout for large files
    """
    if 'file' not in request.files:
        return redirect(url_for('index'))
    
    file = request.files['file']
    
    # Check file size before saving
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Reset
    
    if file_size > 100 * 1024 * 1024:  # 100MB limit
        flash('File too large. Maximum size is 100MB.', 'error')
        return redirect(url_for('index'))
    
    # Continue with normal processing...
    # (rest of convert function)


# Additional helper functions
def extract_incipit_at_position(text, position, word_count):
    """Helper function for incipit extraction"""
    text_before = text[:position]
    if not text_before:
        return ""
    
    # Find sentence start
    sentence_markers = ['. ', '? ', '! ']
    sentence_start = 0
    
    for marker in sentence_markers:
        pos = text_before.rfind(marker)
        if pos > sentence_start:
            sentence_start = pos + len(marker)
    
    sentence = text_before[sentence_start:].strip()
    words = sentence.split()[:word_count]
    
    if words:
        # Clean last word
        words[-1] = re.sub(r'[.,;:!?"\'"]+$', '', words[-1])
    
    return ' '.join(words)


def build_output_streaming(temp_dir, contexts, processed_notes, format_bold):
    """Build output document using streaming approach"""
    # Implementation would modify XML files directly
    # rather than loading entire tree into memory
    pass
