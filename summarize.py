from dotenv import load_dotenv
import anthropic
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import json
import os
import sqlite3

load_dotenv()

# Setup SQLite database
def setup_database():
    # Create a 'data' directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    
    conn = sqlite3.connect('data/summaries.db')
    cursor = conn.cursor()
    
    # Create table for summaries
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            content TEXT,
            summary TEXT,
            tags TEXT,
            author TEXT,
            title TEXT,
            word_count INTEGER,
            has_read BOOLEAN DEFAULT FALSE,
            rating INTEGER CHECK (rating >= 0 AND rating <= 5),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    return conn, cursor

# Add function to save summary
def save_summary(cursor, url, content, summary, tags, word_count, author, title):
    cursor.execute('''
        INSERT INTO summaries (url, author, title, content, summary, tags, word_count)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (url, author, title, content, summary, json.dumps(tags), word_count))

def extract_article_content(url):
    try:
        # Send a GET request with headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract title and author
        title = soup.find('title').get_text() if soup.find('title') else None
        author = None
        author_meta = soup.find('meta', {'name': ['author', 'Author']})
        if author_meta:
            author = author_meta.get('content')
        
        # Remove unwanted elements
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'ads']):
            tag.decompose()
        
        # Look for common article containers
        main_content = soup.find('article') or soup.find('main') or soup.find('div', class_=['content', 'article', 'post'])
        
        if main_content:
            paragraphs = main_content.find_all('p')
        else:
            # Fallback to all paragraphs if no main content container found
            paragraphs = soup.find_all('p')
        
        article_text = ' '.join([p.get_text().strip() for p in paragraphs])
        
        return {
            'content': article_text,
            'title': title,
            'author': author
        }
    
    except requests.RequestException as e:
        return {
            'content': f"Error fetching the article: {str(e)}",
            'title': None,
            'author': None
        }

# Prompt user for URL
url = input("Please enter the URL of the article you want to summarize: ")

# Extract the content
article_data = extract_article_content(url)
article_content = article_data['content']
title = article_data['title']
author = article_data['author']
# print(article_content)
print(f"Title: {title}")
print(f"Author: {author}")


# Calculate and print content length and estimated read time
word_count = len(article_content.split())
# Average reading speed is 200-250 words per minute, using 225 as middle ground
read_time_minutes = round(word_count / 225)

print(f"\nArticle length: {word_count} words")
print(f"Estimated read time: {read_time_minutes} minute{'s' if read_time_minutes != 1 else ''}\n")

client = anthropic.Anthropic()

message_text = f"""Please provide a concise summary of this article:

{article_content}

Also, provide 3-5 relevant topics/tags that this article would fall under.
Output the response in JSON format. Follow this schema:

| Column     | Type     | Description          |
| ---------- | -------- | -------------------- |
| summary    | text     | AI-generated summary |
| tags       | string[] | Article categories   |

Here is an example of the output:
<curly_brace>
    "summary": "This article discusses the impact of artificial intelligence on modern healthcare, focusing on recent breakthroughs in diagnostic imaging and personalized medicine. It explores how machine learning algorithms are improving early disease detection and treatment planning while addressing concerns about data privacy and the doctor-patient relationship.",
    "tags": ["artificial intelligence", "healthcare", "medical technology", "machine learning"]
</curly_brace

"""

message = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1000,
    temperature=0,
    system="You are a professional summarizer. Provide clear, concise summaries while maintaining key information.",
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": message_text
                }
            ]
        }
    ]
)
response_text = message.content[0].text

# Replace curly_brace with actual curly braces if they exist
response_text = response_text.replace("<curly_brace>", "{").replace("</curly_brace", "}")

try:
    response_data = json.loads(response_text)
    summary = response_data["summary"]
    tags = response_data["tags"]
except json.JSONDecodeError as e:
    print(f"Error parsing JSON response: {e}")
    summary = ""
    tags = []

print("SUMMARY\n")
print(summary)
print("\nTAGS\n")
print(tags)
print("\n")

# Add near the top of your main code
conn, cursor = setup_database()

# After getting the summary and tags, save to database
try:
    save_summary(
        cursor=cursor,
        url=url,
        content=article_content,
        summary=summary,
        tags=tags,
        word_count=word_count,
        author=author,
        title=title
    )
    conn.commit()
    print("Summary saved to database successfully!\n")
except sqlite3.Error as e:
    print(f"Error saving to database: {e}\n")

# At the very end of the file
conn.close()