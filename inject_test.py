from database import SessionLocal, Lead, set_setting

db = SessionLocal()
# Ampliar horario para que mande ahora mismo
set_setting(db, "work_hour_start", "0")
set_setting(db, "work_hour_end", "24")

# Insertar el lead falso
lead = Lead(
    email="jeremiasganza14@gmail.com",
    name="Jeremías",
    company="Egasis Prueba S.A.",
    source="Prueba Manual",
    status="pending"
)
db.add(lead)
db.commit()
db.close()
print("Lead inyectado exitosamente y horario ampliado a 24hs.")
