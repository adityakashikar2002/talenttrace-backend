import os
import re
import pdfplumber
from docx import Document
import pandas as pd
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
from flask_cors import CORS
from PIL import Image
import pytesseract
import spacy



def calculate_skill_match(job_skills, resume_skills):
    # Convert job skills to lowercase and strip whitespace
    job_skills_set = set(skill.lower().strip() for skill in job_skills if skill.strip())

    # Preprocess resume skills: normalize and split on common delimiters
    processed_resume_skills = set()
    for skill in resume_skills:
        # Split by common delimiters and words
        split_skills = re.split(r'[,:;\n\s]+', skill.lower())  # Splitting on spaces, commas, colons, etc.
        processed_resume_skills.update(skill.strip() for skill in split_skills if skill.strip())
    
    # Debugging: Print cleaned job and resume skills
    print(f"Job Skills: {job_skills_set}")
    print(f"Resume Skills (Processed): {processed_resume_skills}")

    # Find matched skills
    matched_skills = job_skills_set.intersection(processed_resume_skills)

    # Debugging: Print matched skills
    print(f"Matched Skills: {matched_skills}")

    # Calculate match percentage
    if not job_skills_set:  # Avoid division by zero
        return 0.0
    match_percentage = (len(matched_skills) / len(job_skills_set)) * 100

    return round(match_percentage, 2)  # Return the match as a percentage


# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
UPLOAD_FOLDER = "uploads"
EXCEL_FILE = "resume_data.xlsx"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create uploads folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

import spacy
nlp = spacy.load("en_core_web_sm")

# OCR Function for image extraction
def extract_text_from_image(file_path):
    img = Image.open(file_path)
    text = pytesseract.image_to_string(img)
    return text

# PDF text extraction
def extract_text_from_pdf(file_path):
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text()
    return text

# DOCX text extraction
def extract_text_from_docx(file_path):
    doc = Document(file_path)
    return "\n".join([p.text for p in doc.paragraphs])

# Enhanced details extraction using SpaCy
def extract_details(text):
    details = {}
    doc = nlp(text)

    # Enhanced Name Extraction
    first_line = text.split('\n')[0].strip()
    if len(first_line.split()) <= 3:
        details['Name'] = first_line
    else:
        details['Name'] = "N/A"
    
    if details['Name'] == "N/A" or details['Name'].isdigit():
        name_candidates = [ent.text for ent in doc.ents if ent.label_ == "PERSON"]
        details['Name'] = name_candidates[0] if name_candidates else "N/A"

    # Extract email
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    details['Email'] = re.findall(email_pattern, text)[0] if re.findall(email_pattern, text) else "N/A"

    # Extract phone number
    phone_pattern = r'\b\d{10}\b|\+?\d{1,2}\s?\d{10}\b'
    details['Phone'] = re.findall(phone_pattern, text)[0] if re.findall(phone_pattern, text) else "N/A"

    # Extract skills section and split into individual skills
    skills_keywords = ['skills', 'technical skills', 'key skills']
    skills_section = None

    for keyword in skills_keywords:
        keyword_index = text.lower().find(keyword)
        if keyword_index != -1:
            skills_section = text[keyword_index:keyword_index + 300]  
            break

    if skills_section:
        # Normalize and split the extracted skills
        split_skills = re.split(r'[,:;\n\s]+', skills_section.lower())
        details['Skills'] = ", ".join(skill.strip() for skill in split_skills if skill.strip())
    else:
        details['Skills'] = "N/A"


    # Extract LinkedIn and GitHub
    linkedin_pattern = r'linkedin\.com/in/[A-Za-z0-9_-]+'
    details['LinkedIn'] = re.findall(linkedin_pattern, text)[0] if re.findall(linkedin_pattern, text) else "N/A"

    github_pattern = r'github\.com/[A-Za-z0-9_-]+'
    details['GitHub'] = re.findall(github_pattern, text)[0] if re.findall(github_pattern, text) else "N/A"

    return details

# Append extracted data to Excel
def append_to_excel(data):
    if os.path.exists(EXCEL_FILE):
        df = pd.read_excel(EXCEL_FILE)
        df = pd.concat([df, pd.DataFrame([data])], ignore_index=True)
    else:
        df = pd.DataFrame([data])

    df.to_excel(EXCEL_FILE, index=False)

# Route to handle multiple file uploads
@app.route('/upload', methods=['POST'])
def upload_resumes():
    if 'files' not in request.files or 'job_requirements' not in request.form:
        return jsonify({'error': 'No files or job requirements provided'}), 400

    files = request.files.getlist('files')
    if not files or all(file.filename == '' for file in files):
        return jsonify({'error': 'No selected files'}), 400

    # Parse job requirements
    job_requirements = request.form['job_requirements']
    job_requirements = eval(job_requirements)  # Convert string to dict
    required_skills = job_requirements.get("skills", [])

    all_details = []
    for file in files:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
        file.save(file_path)

        text = ""
        if file.filename.endswith('.pdf'):
            text = extract_text_from_pdf(file_path)
        elif file.filename.endswith('.docx'):
            text = extract_text_from_docx(file_path)
        elif file.filename.lower().endswith(('png', 'jpg', 'jpeg', 'gif', 'bmp')):
            text = extract_text_from_image(file_path)
        else:
            return jsonify({'error': f'Unsupported file type: {file.filename}'}), 400

        details = extract_details(text)

        # Extract skills and calculate match
        # Extract skills and calculate match
        extracted_skills = details.get("Skills", "N/A").split(", ")  # Assume skills are comma-separated
        if extracted_skills == ["N/A"]:
            score = 0  # If no skills found, score is 0
        else:
            score = calculate_skill_match(required_skills.split(", "), extracted_skills)

        details['FitScore'] = score
        all_details.append(details)


    # Append all extracted data to Excel
    for details in all_details:
        append_to_excel(details)

    return jsonify({'message': 'Files processed successfully', 'data': all_details})

# Route to download the Excel file
EXCEL_FILE = "resume_data.xlsx"

@app.route('/download', methods=['GET'])
def download_excel():
    if not os.path.exists(EXCEL_FILE):
        return jsonify({'error': 'No data available'}), 400
    return send_file(EXCEL_FILE, as_attachment=True)

if __name__ == '__main__':
    nlp = spacy.load("en_core_web_sm")
    app.run(host="localhost",port=5000,debug=True)
