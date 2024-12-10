- [ ] cache website's content and summary using SQLite
- [ ] be able to chat with AI about article (may evolve to RAG)
- [ ] determine if the url is readable
- [ ] build tables and data analytics for articles
- [ ] add ability to rate article after reading (0-5 stars)
- [ ] limit how long the article can be
- [x] deploy on fly.io
- [x] build simple frontend UI to connect this to
- [x] convert this to a FastAPI app
- [x] capture title and author if they exists

# SCHEMA

## Database Schema

| Column     | Type     | Description          |
| ---------- | -------- | -------------------- |
| id         | integer  | Primary key          |
| url        | string   | Article URL          |
| content    | text     | Full article content |
| summary    | text     | AI-generated summary |
| tags       | string[] | Article categories   |
| author     | string   | Article author       |
| title      | string   | Article title        |
| word_count | integer  | Total word count     |
| has_read   | boolean  | Read status          |
| rating     | integer  | User rating (0-5)    |

# The Goodreads for web articles?
