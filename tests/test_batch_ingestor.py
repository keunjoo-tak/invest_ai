from app.services.ingestion.batch_ingestor import BatchIngestor


def test_extract_policy_links_filters_menu_links() -> None:
    ing = BatchIngestor()
    html = """
    <html><body>
      <a href="/news/policyNewsList.do">정책뉴스</a>
      <a href="/news/policyNewsView.do?newsId=148960687"><strong>반도체 지원 정책 발표</strong></a>
      <a href="/news/policyNewsView.do?newsId=148960688">${title}</a>
      <a href="#main">본문 바로가기</a>
    </body></html>
    """
    links = ing._extract_policy_links("policy_news", "https://www.korea.kr/news/policyNewsList.do", html, 10)
    assert len(links) == 1
    assert links[0]["url"] == "https://www.korea.kr/news/policyNewsView.do?newsId=148960687"


def test_heuristic_market_relevance_detects_monetary_policy() -> None:
    ing = BatchIngestor()
    result = ing._heuristic_market_relevance(
        "BOK_PUBLICATIONS",
        "통화정책방향",
        "기준금리 동결과 물가, 성장, 환율 전망을 포함한 통화정책 보고서",
        "bok_monetary_policy",
    )
    assert result["should_keep"] is True
    assert result["impact_scope"] == "macro"



def test_extract_naver_section_links_filters_comment_links() -> None:
    ing = BatchIngestor()
    html = """
    <html><body>
      <a href="https://n.news.naver.com/mnews/article/001/0000000001">정치 헤드라인 1</a>
      <a href="https://n.news.naver.com/mnews/article/comment/001/0000000001">댓글</a>
      <a href="/mnews/article/001/0000000002">정치 헤드라인 2</a>
    </body></html>
    """
    links = ing._extract_naver_section_links('politics', '정치', 'https://news.naver.com/section/100', html, 10)
    assert len(links) == 2
    assert all('/article/comment/' not in row['url'] for row in links)
    assert links[0]['section_label'] == '정치'
