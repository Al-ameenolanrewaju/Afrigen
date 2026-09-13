from ..models import GeneratedContent

def publish_newsletter_draft(generated: GeneratedContent) -> dict:
    import os
    if os.environ.get("DRY_RUN") == "true":
        return {"ok": True, "mock": True, "detail": "Dry run newsletter draft"}
        
    from services.newsletter import create_draft
    
    subject = generated.extra_fields.get("subject", "Afrigen Weekly")
    body = generated.content
    
    try:
        issue = create_draft(subject, body, auto_generated=True)
        return {"ok": True, "issue_id": issue.id}
    except Exception as e:
        return {"ok": False, "error": str(e)}
