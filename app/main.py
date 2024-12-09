from functools import lru_cache
from typing import Annotated
from datetime import datetime
import anthropic
from bs4 import BeautifulSoup
import requests
import json
from fastapi import Depends, FastAPI, HTTPException, Query
from sqlmodel import Field, Session, SQLModel, create_engine, select
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "URL Summarizer"
    ANTHROPIC_API_KEY: str
    model_config = SettingsConfigDict(env_file=".env")


class SummaryBase(SQLModel):
    url: str = Field(index=True)
    content: str | None = None
    summary: str | None = None
    tags: str | None = None
    author: str | None = None
    title: str | None = None
    word_count: int | None = None
    has_read: bool = Field(default=False)
    rating: int | None = Field(default=None)
    created_at: datetime | None = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = Field(default_factory=datetime.utcnow)


class Summary(SummaryBase, table=True):
    id: int | None = Field(default=None, primary_key=True)


class SummaryPublic(SummaryBase):
    id: int


class SummaryCreate(SummaryBase):
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SummaryUpdate(SummaryBase):
    url: str | None = None
    content: str | None = None
    summary: str | None = None
    tags: str | None = None
    author: str | None = None
    title: str | None = None
    word_count: int | None = None
    has_read: bool | None = None
    rating: int | None = None


class ArticleRequest(SQLModel):
    url: str


sqlite_file_name = "data/summaries.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, connect_args=connect_args)


@lru_cache
def get_settings():
    return Settings()


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep= Annotated[Settings, Depends(get_settings)]

app = FastAPI()


@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# TODO: change summary to article
@app.post("/summaries/", response_model=SummaryPublic)
def create_summary(summary: SummaryCreate, session: SessionDep, settings: SettingsDep):
    if not summary.content:
        raise HTTPException(status_code=400, detail="Content is required for summary generation")
    
    # Generate summary using Anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    message_text = f"""Please provide a concise summary of this article:

    {summary.content}

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
    </curly_brace>

    """

    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            temperature=0,
            system="You are a professional summarizer. Provide clear, concise summaries while maintaining key information.",
            messages=[
                {
                    "role": "user",
                    "content": message_text
                }
            ]
        )
        response_text = message.content[0].text
        response_data = json.loads(response_text)
        
        # Create and save summary
        summary_create = SummaryCreate(
            url=summary.url,
            content=summary.content,
            summary=response_data["summary"],
            tags=",".join(response_data["tags"]),
            author=summary.author,
            title=summary.title,
            word_count=summary.word_count
        )
        
        db_summary = Summary.model_validate(summary_create)
        session.add(db_summary)
        session.commit()
        session.refresh(db_summary)
        
        return db_summary

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating summary: {str(e)}")



@app.get("/summaries/", response_model=list[SummaryPublic])
def read_summaries(
    session: SessionDep,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
):
    summaries = session.exec(select(Summary).offset(offset).limit(limit)).all()
    return summaries


@app.get("/summaries/{summary_id}", response_model=SummaryPublic)
def read_summary(summary_id: int, session: SessionDep):
    summary = session.get(Summary, summary_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    return summary


@app.patch("/summaries/{summary_id}", response_model=SummaryPublic)
def update_summary(summary_id: int, summary: SummaryUpdate, session: SessionDep):
    summary_db = session.get(Summary, summary_id)
    if not summary_db:
        raise HTTPException(status_code=404, detail="Summary not found")
    summary_data = summary.model_dump(exclude_unset=True)
    summary_data["updated_at"] = datetime.utcnow()
    summary_db.sqlmodel_update(summary_data)
    session.add(summary_db)
    session.commit()
    session.refresh(summary_db)
    return summary_db


@app.delete("/summaries/{summary_id}")
def delete_summary(summary_id: int, session: SessionDep):
    summary = session.get(Summary, summary_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    session.delete(summary)
    session.commit()
    return {"ok": True}


@app.post("/summarize/", response_model=SummaryPublic)
async def summarize_article(article: ArticleRequest, session: SessionDep, settings: SettingsDep):
    def extract_article_content(url: str):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            title = soup.find('title').get_text() if soup.find('title') else None
            author = None
            author_meta = soup.find('meta', {'name': ['author', 'Author']})
            if author_meta:
                author = author_meta.get('content')
            
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'ads']):
                tag.decompose()
            
            main_content = soup.find('article') or soup.find('main') or soup.find('div', class_=['content', 'article', 'post'])
            
            if main_content:
                paragraphs = main_content.find_all('p')
            else:
                paragraphs = soup.find_all('p')
            
            article_text = ' '.join([p.get_text().strip() for p in paragraphs])
            
            return {
                'content': article_text,
                'title': title,
                'author': author
            }
        except requests.RequestException as e:
            raise HTTPException(status_code=400, detail=f"Error fetching article: {str(e)}")

    # Extract content
    article_data = extract_article_content(article.url)
    article_content = article_data['content']
    word_count = len(article_content.split())

    # Generate summary using Anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

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
    </curly_brace>

    """

    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            temperature=0,
            system="You are a professional summarizer. Provide clear, concise summaries while maintaining key information.",
            messages=[
                {
                    "role": "user",
                    "content": message_text
                }
            ]
        )
        response_text = message.content[0].text
        response_data = json.loads(response_text)
        
        # Create and save summary
        summary_create = SummaryCreate(
            url=article.url,
            content=article_content,
            summary=response_data["summary"],
            tags=",".join(response_data["tags"]),
            author=article_data["author"],
            title=article_data["title"],
            word_count=word_count
        )
        
        db_summary = Summary.model_validate(summary_create)
        session.add(db_summary)
        session.commit()
        session.refresh(db_summary)
        
        return db_summary

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating summary: {str(e)}")
