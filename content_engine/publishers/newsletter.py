from ..models import GeneratedContent

def publish_newsletter_draft(generated: GeneratedContent) -> dict:
    import os
    if os.environ.get("DRY_RUN") == "true":
        return {"ok": True, "mock": True, "detail": "Dry run newsletter draft"}
        
    from services.user_content import create_user_content
    
    subject = generated.extra_fields.get("subject", "Afrigen Weekly")
    body = generated.content
    
    try:
        # Default user_id=1 for automation generated newsletter
        issue = create_user_content(
            user_id=1, 
            content_type="newsletter", 
            title=subject, 
            body=body, 
            status="draft", 
            source="automation",
            provider_used="ContentEngine/Newsletter"
        )
        return {"ok": True, "issue_id": issue.id}
    except Exception as e:
        return {"ok": False, "error": str(e)}
