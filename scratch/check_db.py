from database import SessionLocal, Lead, SentEmail

db = SessionLocal()
print("=== LEADS IN DB ===")
leads = db.query(Lead).all()
for l in leads:
    if "miempresa" in l.email or "empresa" in l.email or l.id > 10:
        print(f"Lead ID {l.id}: {l.email} - status: {l.status} - company: {l.company}")
    else:
        # Just print first 5 leads
        if l.id <= 5:
            print(f"Lead ID {l.id}: {l.email} - status: {l.status} - company: {l.company}")

print("\n=== LAST 15 SENT EMAILS ===")
sent = db.query(SentEmail).order_by(SentEmail.id.desc()).limit(15).all()
for s in sent:
    print(f"Sent ID {s.id}: Lead ID {s.lead_id} - subject: {s.subject} - sent_at: {s.sent_at}")
    # Check if we can find miempresa in body or recipient
    lead = db.query(Lead).filter(Lead.id == s.lead_id).first()
    if lead and ("miempresa" in lead.email or "empresa" in lead.email):
         print(f"   => Recipient was: {lead.email}")

db.close()
