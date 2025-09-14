import os
import re
import json
import requests
import trafilatura
from bs4 import BeautifulSoup
import bleach
from urllib.parse import urljoin, urlparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from datetime import datetime
from werkzeug.utils import secure_filename
import logging
import socket
import ipaddress
from typing import Dict, List, Tuple, Optional

# Configure logging for debugging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Static list of common stopwords to avoid downloading NLTK data
STOPWORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'been', 'by', 'for', 'from',
    'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the', 'to',
    'was', 'will', 'with', 'would', 'have', 'had', 'this', 'they', 'we', 'you',
    'your', 'but', 'can', 'could', 'do', 'does', 'did', 'not', 'no', 'or',
    'there', 'their', 'them', 'then', 'than', 'what', 'when', 'where', 'who',
    'why', 'how', 'about', 'after', 'all', 'also', 'any', 'because', 'before',
    'being', 'between', 'both', 'each', 'few', 'more', 'most', 'other', 'some',
    'such', 'only', 'own', 'same', 'so', 'through', 'very', 'way', 'well'
}

class WebContentImporter:
    """Handles web content scraping, image downloading, and quiz generation"""
    
    def __init__(self, upload_folder='static/resources', max_images=10, max_image_size=2*1024*1024, timeout=15):
        self.upload_folder = upload_folder
        self.max_images = max_images
        self.max_image_size = max_image_size
        self.timeout = timeout
        
        # Ensure upload directory exists
        os.makedirs(upload_folder, exist_ok=True)
        
        # Security: Define blocked IP ranges to prevent SSRF attacks
        self.blocked_networks = [
            ipaddress.ip_network('127.0.0.0/8'),      # localhost
            ipaddress.ip_network('10.0.0.0/8'),       # RFC1918 private
            ipaddress.ip_network('172.16.0.0/12'),    # RFC1918 private
            ipaddress.ip_network('192.168.0.0/16'),   # RFC1918 private
            ipaddress.ip_network('169.254.0.0/16'),   # link-local
            ipaddress.ip_network('224.0.0.0/4'),      # multicast
            ipaddress.ip_network('::1/128'),          # IPv6 localhost
            ipaddress.ip_network('fc00::/7'),         # IPv6 private
            ipaddress.ip_network('fe80::/10'),        # IPv6 link-local
        ]
        
        # Allowed HTML tags for sanitization
        self.allowed_tags = ['p', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'em', 'u', 'b', 'i', 
                           'ul', 'ol', 'li', 'a', 'img', 'blockquote', 'pre', 'code', 'div', 'span']
        self.allowed_attributes = {
            'a': ['href', 'title'],
            'img': ['src', 'alt', 'title', 'width', 'height'],
            'div': ['class'],
            'span': ['class']
        }
    
    def _validate_url_security(self, url: str) -> None:
        """
        Validate URL to prevent SSRF attacks by blocking access to internal/private networks
        """
        parsed = urlparse(url)
        
        # Only allow HTTP/HTTPS schemes
        if parsed.scheme not in ['http', 'https']:
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
        
        if not parsed.netloc:
            raise ValueError("Invalid URL: no network location")
        
        # Extract hostname (remove port if present)
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("Invalid URL: could not extract hostname")
        
        try:
            # Resolve hostname to IP address
            ip_info = socket.getaddrinfo(hostname, None)
            if not ip_info:
                raise ValueError(f"Could not resolve hostname: {hostname}")
            
            # Check all resolved IPs
            for ip_data in ip_info:
                ip_str = ip_data[4][0]  # Extract IP string from tuple
                try:
                    ip_addr = ipaddress.ip_address(ip_str)
                    
                    # Check against blocked networks
                    for blocked_network in self.blocked_networks:
                        if ip_addr in blocked_network:
                            raise ValueError(f"Access to {ip_str} ({hostname}) is blocked for security reasons")
                    
                    logger.debug(f"URL security check passed for {hostname} -> {ip_str}")
                    
                except ValueError as e:
                    if "is blocked" in str(e):
                        raise e
                    logger.warning(f"Could not parse IP address {ip_str}: {e}")
                    continue
                    
        except socket.gaierror as e:
            raise ValueError(f"DNS resolution failed for {hostname}: {e}")
        except Exception as e:
            raise ValueError(f"Security validation failed for {hostname}: {e}")
    
    def _secure_fetch_with_redirects(self, url: str, max_redirects: int = 5, max_content_size: int = 5*1024*1024) -> str:
        """
        Securely fetch URL content with manual redirect handling, SSRF protection, and size limits
        """
        current_url = url
        redirect_count = 0
        
        while redirect_count <= max_redirects:
            # Validate current URL
            self._validate_url_security(current_url)
            
            # Fetch without following redirects, stream to enforce size limits
            response = requests.get(current_url, timeout=self.timeout, allow_redirects=False, stream=True)
            
            # If not a redirect, return content with size limits
            if response.status_code not in [301, 302, 303, 307, 308]:
                response.raise_for_status()
                
                # Check Content-Length if provided
                content_length = response.headers.get('Content-Length')
                if content_length and int(content_length) > max_content_size:
                    raise ValueError(f"Content too large: {content_length} bytes (max {max_content_size})")
                
                # Stream content with size limit enforcement
                content_bytes = b''
                for chunk in response.iter_content(chunk_size=8192):
                    if len(content_bytes) + len(chunk) > max_content_size:
                        raise ValueError(f"Content exceeds size limit: {max_content_size} bytes")
                    content_bytes += chunk
                
                return content_bytes.decode('utf-8', errors='replace')
            
            # Handle redirect
            redirect_url = response.headers.get('Location')
            if not redirect_url:
                break
            
            # Make relative redirects absolute
            if not redirect_url.startswith(('http://', 'https://')):
                redirect_url = urljoin(current_url, redirect_url)
            
            current_url = redirect_url
            redirect_count += 1
        
        if redirect_count > max_redirects:
            raise ValueError(f"Too many redirects (>{max_redirects})")
        
        # Final request if we broke out of loop with size limits
        self._validate_url_security(current_url)
        response = requests.get(current_url, timeout=self.timeout, allow_redirects=False, stream=True)
        response.raise_for_status()
        
        # Check Content-Length if provided
        content_length = response.headers.get('Content-Length')
        if content_length and int(content_length) > max_content_size:
            raise ValueError(f"Content too large: {content_length} bytes (max {max_content_size})")
        
        # Stream content with size limit enforcement
        content_bytes = b''
        for chunk in response.iter_content(chunk_size=8192):
            if len(content_bytes) + len(chunk) > max_content_size:
                raise ValueError(f"Content exceeds size limit: {max_content_size} bytes")
            content_bytes += chunk
        
        return content_bytes.decode('utf-8', errors='replace')
    
    def scrape_url_content(self, url: str, include_images: bool = True) -> Dict:
        """
        Scrape content from URL including text and optionally images
        Returns: {text: str, html: str, images: List[str], title: str}
        """
        try:
            logger.info(f"Scraping content from: {url}")
            
            # Parse URL for title fallback
            parsed = urlparse(url)
            
            # Get main text content using secure fetch with redirect protection
            downloaded = self._secure_fetch_with_redirects(url)
            if not downloaded:
                raise ValueError("Failed to fetch URL content")
            
            main_text = trafilatura.extract(downloaded)
            if not main_text:
                raise ValueError("Failed to extract text from URL")
            
            # Parse HTML for images and structure
            soup = BeautifulSoup(downloaded, 'html.parser')
            
            # Extract title
            title = None
            if soup.title:
                title = soup.title.get_text().strip()
            else:
                # Try to find h1 as fallback
                h1 = soup.find('h1')
                if h1:
                    title = h1.get_text().strip()
            
            if not title:
                title = f"Content from {parsed.netloc}"
            
            # Extract and download images if requested
            downloaded_images = []
            processed_html = main_text  # Start with plain text
            
            if include_images:
                downloaded_images = self._download_images(soup, url)
                # Create basic HTML structure with images
                processed_html = self._create_html_with_images(main_text, downloaded_images)
            
            # Sanitize HTML
            sanitized_html = bleach.clean(processed_html, tags=self.allowed_tags, 
                                        attributes=self.allowed_attributes, strip=True)
            
            return {
                'text': main_text,
                'html': sanitized_html,
                'images': downloaded_images,
                'title': title[:200],  # Limit title length
                'url': url
            }
            
        except Exception as e:
            logger.error(f"Error scraping URL {url}: {str(e)}")
            raise
    
    def _download_images(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Download images from the page and return list of local paths"""
        downloaded_images = []
        img_tags = soup.find_all('img', limit=self.max_images)
        
        for img_tag in img_tags:
            try:
                img_src = img_tag.get('src') or img_tag.get('data-src')
                if not img_src:
                    continue
                
                # Resolve relative URLs
                img_url = urljoin(base_url, img_src)
                parsed_img = urlparse(img_url)
                
                # Apply security validation to image URLs
                try:
                    self._validate_url_security(img_url)
                except ValueError as e:
                    logger.warning(f"Skipping image due to security check: {e}")
                    continue
                
                # Download image with redirect protection
                response = requests.get(img_url, timeout=self.timeout, stream=True, allow_redirects=False)
                
                # Handle redirects manually with security validation
                redirect_count = 0
                while response.status_code in [301, 302, 303, 307, 308] and redirect_count < 5:
                    redirect_url = response.headers.get('Location')
                    if not redirect_url:
                        break
                    
                    # Make relative redirects absolute
                    if not redirect_url.startswith(('http://', 'https://')):
                        redirect_url = urljoin(img_url, redirect_url)
                    
                    # Validate redirect target
                    try:
                        self._validate_url_security(redirect_url)
                    except ValueError as e:
                        logger.warning(f"Skipping image redirect due to security check: {e}")
                        break
                    
                    img_url = redirect_url
                    parsed_img = urlparse(img_url)
                    response = requests.get(img_url, timeout=self.timeout, stream=True, allow_redirects=False)
                    redirect_count += 1
                
                if not response.ok:
                    continue
                
                # Check content type and block SVG for security (XSS risk)
                content_type = response.headers.get('Content-Type', '').lower()
                if 'svg' in content_type:
                    logger.warning(f"Blocked SVG image for security: {img_url}")
                    continue
                
                # Only allow safe image types
                if not any(img_type in content_type for img_type in ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']):
                    continue
                
                content_length = int(response.headers.get('Content-Length', 0))
                if content_length > self.max_image_size:
                    continue
                
                # Generate secure filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
                original_filename = os.path.basename(parsed_img.path) or 'image'
                # Get file extension from content type
                ext = '.jpg'  # default
                if 'png' in content_type:
                    ext = '.png'
                elif 'gif' in content_type:
                    ext = '.gif'
                elif 'webp' in content_type:
                    ext = '.webp'
                
                filename = f"{timestamp}{secure_filename(original_filename.split('.')[0])}{ext}"
                filepath = os.path.join(self.upload_folder, filename)
                
                # Save image with byte limit enforcement
                bytes_written = 0
                with open(filepath, 'wb') as f:
                    try:
                        for chunk in response.iter_content(chunk_size=8192):
                            if bytes_written + len(chunk) > self.max_image_size:
                                # Remove partial file if size exceeded
                                f.close()
                                os.remove(filepath)
                                logger.warning(f"Image {img_url} exceeded size limit, removed partial file")
                                break
                            f.write(chunk)
                            bytes_written += len(chunk)
                    except Exception as e:
                        # Clean up partial file on any error
                        f.close()
                        if os.path.exists(filepath):
                            os.remove(filepath)
                        logger.warning(f"Error downloading {img_url}: {e}")
                        continue
                
                # Validate image type using magic bytes for security
                try:
                    from PIL import Image
                    with Image.open(filepath) as img:
                        # Verify it's a safe image format (not SVG or other)
                        if img.format not in ['JPEG', 'PNG', 'GIF', 'WEBP']:
                            os.remove(filepath)
                            logger.warning(f"Blocked unsafe image format {img.format}: {img_url}")
                            continue
                except Exception as e:
                    # Remove if not a valid image
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    logger.warning(f"Invalid image file removed {img_url}: {e}")
                    continue
                
                downloaded_images.append(filename)
                logger.info(f"Downloaded image: {filename}")
                
            except Exception as e:
                logger.warning(f"Failed to download image {img_src}: {str(e)}")
                continue
        
        return downloaded_images
    
    def _create_html_with_images(self, text: str, images: List[str]) -> str:
        """Create HTML content with embedded images"""
        # Convert text to paragraphs
        paragraphs = text.split('\n\n')
        html_parts = []
        
        for i, paragraph in enumerate(paragraphs):
            if paragraph.strip():
                html_parts.append(f"<p>{paragraph.strip()}</p>")
                
                # Insert images between paragraphs
                if images and i < len(images):
                    img_path = f"/static/resources/{images[i]}"
                    html_parts.append(f'<img src="{img_path}" alt="Content image" style="max-width: 100%; height: auto; margin: 10px 0;" />')
        
        # Add remaining images at the end
        remaining_images = images[len(paragraphs):]
        for image in remaining_images:
            img_path = f"/static/resources/{image}"
            html_parts.append(f'<img src="{img_path}" alt="Content image" style="max-width: 100%; height: auto; margin: 10px 0;" />')
        
        return '\n'.join(html_parts)
    
    def generate_quiz(self, text: str, num_mcq: int = 5, num_tf: int = 3) -> Dict:
        """
        Generate quiz questions from text using Python NLP techniques
        Returns: {questions: List[Dict]}
        """
        try:
            logger.info(f"Generating quiz with {num_mcq} MCQ and {num_tf} T/F questions")
            
            if len(text) < 100:
                raise ValueError("Text too short to generate meaningful questions")
            
            # Preprocess text
            sentences = self._extract_sentences(text)
            if len(sentences) < 3:
                raise ValueError("Not enough content to generate quiz questions")
            
            # Extract keywords using TF-IDF
            keywords = self._extract_keywords(text)
            
            # Generate different types of questions
            questions = []
            
            # Generate multiple choice questions
            mcq_questions = self._generate_mcq_questions(sentences, keywords, num_mcq)
            questions.extend(mcq_questions)
            
            # Generate true/false questions
            tf_questions = self._generate_tf_questions(sentences, num_tf)
            questions.extend(tf_questions)
            
            return {"questions": questions}
            
        except Exception as e:
            logger.error(f"Error generating quiz: {str(e)}")
            # Return basic fallback quiz
            return {
                "questions": [
                    {
                        "type": "multiple_choice",
                        "question": "What is the main topic of this content?",
                        "options": ["Technology", "Education", "Science", "General Knowledge"],
                        "answer_index": 0,
                        "explanation": "Based on the imported content"
                    }
                ]
            }
    
    def _extract_sentences(self, text: str) -> List[str]:
        """Extract and clean sentences from text"""
        # Simple sentence splitting on punctuation
        sentences = re.split(r'[.!?]+', text)
        
        # Clean and filter sentences
        clean_sentences = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 20 and len(sentence) < 300:  # Filter by length
                clean_sentences.append(sentence)
        
        return clean_sentences[:50]  # Limit to first 50 sentences
    
    def _extract_keywords(self, text: str, max_features: int = 20) -> List[str]:
        """Extract keywords using TF-IDF"""
        try:
            # Preprocess text - convert to lowercase and remove stopwords
            words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
            filtered_words = [word for word in words if word not in STOPWORDS]
            processed_text = ' '.join(filtered_words)
            
            # Use TF-IDF to find important terms
            vectorizer = TfidfVectorizer(max_features=max_features, ngram_range=(1, 2))
            tfidf_matrix = vectorizer.fit_transform([processed_text])
            
            # Get feature names and scores
            feature_names = vectorizer.get_feature_names_out()
            scores = tfidf_matrix.toarray()[0]
            
            # Create keyword list with scores
            keywords_with_scores = list(zip(feature_names, scores))
            keywords_with_scores.sort(key=lambda x: x[1], reverse=True)
            
            # Return top keywords
            return [kw[0] for kw in keywords_with_scores[:max_features]]
            
        except Exception as e:
            logger.warning(f"TF-IDF extraction failed: {str(e)}, using fallback")
            # Fallback: simple word frequency
            words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
            filtered_words = [word for word in words if word not in STOPWORDS]
            word_freq = {}
            for word in filtered_words:
                word_freq[word] = word_freq.get(word, 0) + 1
            
            sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
            return [word[0] for word in sorted_words[:max_features]]
    
    def _generate_mcq_questions(self, sentences: List[str], keywords: List[str], num_questions: int) -> List[Dict]:
        """Generate multiple choice questions"""
        questions = []
        
        # Pattern 1: Definition/concept questions
        definition_patterns = [
            r'(.+?)\s+is\s+(.+?)[\.\,]',
            r'(.+?)\s+are\s+(.+?)[\.\,]',
            r'(.+?)\s+refers to\s+(.+?)[\.\,]',
            r'(.+?)\s+means\s+(.+?)[\.\,]'
        ]
        
        for sentence in sentences[:20]:  # Limit search
            for pattern in definition_patterns:
                match = re.search(pattern, sentence, re.IGNORECASE)
                if match and len(questions) < num_questions:
                    concept = match.group(1).strip()
                    definition = match.group(2).strip()
                    
                    if len(concept) > 3 and len(concept) < 50 and len(definition) > 10:
                        # Generate distractors from other keywords
                        distractors = self._generate_distractors(concept, keywords, 3)
                        
                        question = {
                            "type": "multiple_choice",
                            "question": f"What is {definition}?",
                            "options": [concept] + distractors,
                            "answer_index": 0,
                            "explanation": f"Based on the content: {sentence[:100]}..."
                        }
                        questions.append(question)
        
        # Pattern 2: Numeric/factual questions
        numeric_pattern = r'(\d+(?:\.\d+)?)\s*(%|percent|dollars?|years?|months?|days?|people|users|companies)'
        
        for sentence in sentences[:30]:
            matches = re.findall(numeric_pattern, sentence, re.IGNORECASE)
            if matches and len(questions) < num_questions:
                value, unit = matches[0]
                
                question_text = re.sub(r'\d+(?:\.\d+)?', '___', sentence, count=1)
                question_text = question_text[:100] + "?" if len(question_text) > 100 else question_text + "?"
                
                # Generate numeric distractors
                try:
                    num_value = float(value)
                    distractors = [
                        str(int(num_value * 0.8)),
                        str(int(num_value * 1.2)), 
                        str(int(num_value * 1.5))
                    ]
                    
                    question = {
                        "type": "multiple_choice",
                        "question": question_text,
                        "options": [value] + distractors,
                        "answer_index": 0,
                        "explanation": f"From the content: {sentence[:100]}..."
                    }
                    questions.append(question)
                except:
                    continue
        
        # Fill remaining slots with keyword-based questions
        while len(questions) < num_questions and keywords:
            keyword = keywords[len(questions) % len(keywords)]
            
            # Find sentence containing the keyword
            keyword_sentence = None
            for sentence in sentences:
                if keyword.lower() in sentence.lower():
                    keyword_sentence = sentence
                    break
            
            if keyword_sentence:
                distractors = self._generate_distractors(keyword, keywords, 3)
                question = {
                    "type": "multiple_choice", 
                    "question": f"Which term is most relevant to: '{keyword_sentence[:80]}...'?",
                    "options": [keyword.title()] + [d.title() for d in distractors],
                    "answer_index": 0,
                    "explanation": "Based on context analysis"
                }
                questions.append(question)
            else:
                break
        
        return questions
    
    def _generate_tf_questions(self, sentences: List[str], num_questions: int) -> List[Dict]:
        """Generate true/false questions"""
        questions = []
        
        for sentence in sentences[:num_questions*3]:  # More sentences to choose from
            if len(questions) >= num_questions:
                break
                
            sentence = sentence.strip()
            if len(sentence) < 30 or len(sentence) > 200:
                continue
            
            # Create true statement (original)
            if len(questions) % 2 == 0:  # Make ~50% true
                question = {
                    "type": "true_false",
                    "question": sentence,
                    "answer": True,
                    "explanation": "This statement is directly from the content"
                }
            else:
                # Create false statement by negation or modification
                false_sentence = self._create_false_statement(sentence)
                question = {
                    "type": "true_false", 
                    "question": false_sentence,
                    "answer": False,
                    "explanation": "This statement has been modified from the original content"
                }
            
            questions.append(question)
        
        return questions
    
    def _create_false_statement(self, sentence: str) -> str:
        """Create a false version of a true statement"""
        # Simple negation patterns
        if ' is ' in sentence.lower():
            return sentence.replace(' is ', ' is not ', 1)
        elif ' are ' in sentence.lower():
            return sentence.replace(' are ', ' are not ', 1)
        elif ' can ' in sentence.lower():
            return sentence.replace(' can ', ' cannot ', 1)
        elif ' will ' in sentence.lower():
            return sentence.replace(' will ', ' will not ', 1)
        else:
            # Add "not" after first verb-like word
            words = sentence.split()
            for i, word in enumerate(words):
                if word.lower() in ['has', 'have', 'was', 'were', 'does', 'did']:
                    words.insert(i+1, 'not')
                    return ' '.join(words)
            
            # Fallback: just add "not" 
            return f"It is not true that {sentence.lower()}"
    
    def _generate_distractors(self, correct_answer: str, keywords: List[str], count: int) -> List[str]:
        """Generate plausible wrong answers"""
        distractors = []
        correct_lower = correct_answer.lower()
        
        # Filter keywords to avoid the correct answer
        available_keywords = [kw for kw in keywords if kw.lower() != correct_lower and kw not in distractors]
        
        # Add keywords as distractors
        for keyword in available_keywords[:count]:
            if len(distractors) < count:
                distractors.append(keyword.title())
        
        # Fill remaining with generic distractors if needed
        generic_distractors = ["Technology", "Process", "System", "Method", "Approach", "Solution", "Strategy", "Framework"]
        for generic in generic_distractors:
            if len(distractors) < count and generic.lower() not in [d.lower() for d in distractors] and generic.lower() != correct_lower:
                distractors.append(generic)
        
        # Ensure we have enough distractors
        while len(distractors) < count:
            distractors.append(f"Option {len(distractors) + 1}")
        
        return distractors[:count]