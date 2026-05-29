document.addEventListener("DOMContentLoaded", () => {
    
    // Navegación de Pestañas
    const navLinks = document.querySelectorAll("nav a");
    const sections = document.querySelectorAll(".view-section");

    navLinks.forEach(link => {
        link.addEventListener("click", (e) => {
            e.preventDefault();
            navLinks.forEach(l => l.classList.remove("active"));
            link.classList.add("active");
            
            const targetId = link.getAttribute("data-target");
            sections.forEach(sec => {
                sec.style.display = sec.id === targetId ? "block" : "none";
            });
            
            if(targetId === 'inbox') fetchReplies();
            if(targetId === 'meetings') fetchMeetings();
            if(targetId === 'learnings') fetchLearnings();
            if(targetId === 'settings') fetchSettings();
        });
    });

    // Terminal por WebSockets con Reconexión Automática
    const terminalOutput = document.getElementById("terminal-output");
    let ws;
    
    function connectWebSocket() {
        const protocol = window.location.protocol === "https:" ? "wss" : "ws";
        ws = new WebSocket(`${protocol}://${window.location.host}/ws/logs`);

        ws.onmessage = function(event) {
            const line = document.createElement("div");
            line.className = "log-line";
            
            let text = event.data;
            if(text.includes("✅")) text = `<span style="color: var(--success)">${text}</span>`;
            if(text.includes("❌") || text.includes("⚠️") || text.includes("🛑") || text.includes("Error")) text = `<span style="color: var(--danger)">${text}</span>`;
            if(text.includes("🎯")) text = `<span style="color: #ffbd2e; font-weight: bold;">${text}</span>`;
            if(text.includes("🚀") || text.includes("=")){
                text = `<span style="color: var(--primary); font-weight: bold;">${text}</span>`;
            }
            
            line.innerHTML = text;
            terminalOutput.appendChild(line);
            terminalOutput.scrollTop = terminalOutput.scrollHeight;
        };

        ws.onclose = function() {
            console.log("WebSocket cerrado. Reintentando conectar en 3 segundos...");
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = function(err) {
            console.error("Error en WebSocket: ", err);
        };
    }
    
    connectWebSocket();

    // Métricas del Dashboard
    async function fetchMetrics() {
        try {
            const res = await fetch("/api/metrics");
            const data = await res.json();
            
            document.getElementById("metric-sent").innerText = data.sent_today;
            document.getElementById("metric-limit").innerText = data.daily_limit;
            document.getElementById("metric-total").innerText = data.total_leads;
            document.getElementById("metric-replies").innerText = data.total_replies;
            
            const pct = Math.min(100, (data.sent_today / data.daily_limit) * 100);
            document.getElementById("bar-sent").style.width = pct + "%";
            
            const isBotRunning = (data.bot_status === "running");
            const statusIndicator = document.getElementById("bot-status-indicator");
            const statusText = document.getElementById("bot-status-text");
            
            if (isBotRunning) {
                statusIndicator.classList.add("running");
                statusText.innerText = "En ejecución";
            } else {
                statusIndicator.classList.remove("running");
                statusText.innerText = "Detenido";
            }
        } catch (e) {
            console.error(e);
        }
    }

    let currentReplies = [];

    async function fetchReplies() {
        const res = await fetch("/api/replies");
        currentReplies = await res.json();
        const feed = document.getElementById("replies-feed");
        if (!feed) return;
        feed.innerHTML = "";
        
        if (currentReplies.length === 0) {
            feed.innerHTML = `<div class="glass-panel p-4 text-center text-sm" style="color: var(--text-muted);">No hay correos en la bandeja de entrada.</div>`;
            return;
        }
        
        currentReplies.forEach(reply => {
            const card = document.createElement("div");
            card.className = "glass-panel p-4";
            card.style.display = "flex";
            card.style.flexDirection = "column";
            card.style.gap = "16px";
            card.style.position = "relative";
            card.style.overflow = "hidden";
            
            // Efecto de brillo sutil según clasificación
            const glowColor = reply.classification === 'interested' ? "rgba(56, 176, 0, 0.15)" : 
                              reply.classification === 'not_interested' ? "rgba(255, 90, 95, 0.15)" : "rgba(157, 78, 221, 0.15)";
            card.style.boxShadow = `inset 0 0 40px ${glowColor}, 0 4px 15px rgba(0,0,0,0.2)`;

            const isPending = reply.processed_status === 'pending_approval';

            let classBadge = "";
            if (reply.classification === 'interested') classBadge = `<span class="badge" style="background: rgba(56, 176, 0, 0.2); color: #38b000; border: 1px solid #38b000;">Positivo / Interesado</span>`;
            else if (reply.classification === 'not_interested') classBadge = `<span class="badge" style="background: rgba(255, 90, 95, 0.2); color: var(--danger); border: 1px solid var(--danger);">Rechazo / No Interesado</span>`;
            else classBadge = `<span class="badge" style="background: rgba(157, 78, 221, 0.2); color: #c77dff; border: 1px solid #c77dff;">${reply.classification}</span>`;

            let statusBadge = isPending ? `<span class="badge bg-warning" style="color:#000;">Requiere Acción</span>` : 
                              reply.processed_status === 'replied' ? `<span class="badge bg-success">Respondido</span>` : 
                              `<span class="badge" style="background:rgba(255,255,255,0.1);">${reply.processed_status}</span>`;

            card.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <div>
                        <h3 style="margin-bottom: 4px; font-size: 1.1rem; color: #fff;">${reply.subject || 'Sin Asunto'}</h3>
                        <p class="text-sm" style="color: var(--text-muted);">De: <strong>${reply.from_email}</strong></p>
                        <div style="margin-top: 8px;">${classBadge}</div>
                    </div>
                    <div>
                        ${statusBadge}
                        <button class="btn-delete-subtle btn-delete-lead" data-lead-id="${reply.lead_id}" style="margin-left: 12px; font-size: 1rem;" title="Eliminar Lead">🗑️</button>
                    </div>
                </div>

                <div style="background: rgba(0,0,0,0.2); padding: 16px; border-radius: 8px; font-size: 0.95rem; color: #ddd; white-space: pre-wrap; max-height: 200px; overflow-y: auto; border: 1px solid rgba(255,255,255,0.05);">
                    ${reply.body || 'Sin contenido'}
                </div>

                ${isPending ? `
                <div style="margin-top: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-weight: 600; font-size: 0.9rem; color: #fff; display: flex; align-items: center; gap: 6px;">
                            Respuesta sugerida:
                        </span>
                    </div>
                    
                    <input type="text" id="subj-${reply.id}" value="${reply.proposed_subject || 'Re: ' + (reply.subject || '')}" 
                           style="width: 100%; padding: 12px; margin-bottom: 8px; border: 1px solid var(--border); border-radius: 6px; background: rgba(18, 16, 28, 0.6); color: #fff; outline: none; font-size: 0.9rem;">
                    
                    <textarea id="body-${reply.id}" rows="6" 
                              style="width: 100%; padding: 12px; border: 1px solid var(--border); border-radius: 6px; background: rgba(18, 16, 28, 0.6); color: #fff; outline: none; font-size: 0.95rem; resize: vertical; line-height: 1.5;">${reply.proposed_reply || ''}</textarea>
                    
                    <div style="display: flex; gap: 12px; justify-content: flex-end; margin-top: 12px;">
                        <button class="btn btn-secondary btn-dismiss-inline" data-id="${reply.id}">Descartar</button>
                        <button class="btn btn-primary btn-send-inline" data-id="${reply.id}">Aprobar y Enviar 🚀</button>
                    </div>
                </div>
                ` : ``}
            `;
            feed.appendChild(card);
        });

        // Event listeners para eliminar
        feed.querySelectorAll(".btn-delete-lead").forEach(btn => {
            btn.addEventListener("click", () => {
                const leadId = parseInt(btn.getAttribute("data-lead-id"));
                if (leadId && confirm("¿Eliminar este cliente potencial por completo?")) {
                    deleteLead(leadId);
                }
            });
        });

        // Event listeners para descartar
        feed.querySelectorAll(".btn-dismiss-inline").forEach(btn => {
            btn.addEventListener("click", async () => {
                const id = btn.getAttribute("data-id");
                if (confirm("¿Estás seguro de que quieres descartar esta respuesta e ignorarla?")) {
                    btn.innerText = "...";
                    const res = await fetch(`/api/replies/${id}/dismiss`, { method: "POST" });
                    if (res.ok) fetchReplies();
                }
            });
        });

        // Event listeners para enviar
        feed.querySelectorAll(".btn-send-inline").forEach(btn => {
            btn.addEventListener("click", async () => {
                const id = btn.getAttribute("data-id");
                const subj = document.getElementById(`subj-${id}`).value;
                const body = document.getElementById(`body-${id}`).value;
                
                if (!subj || !body) {
                    alert("Asunto y cuerpo son obligatorios.");
                    return;
                }
                
                btn.innerText = "Enviando...";
                btn.disabled = true;
                
                const res = await fetch(`/api/replies/${id}/approve`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ subject: subj, body: body })
                });
                
                if (res.ok) {
                    fetchReplies();
                    fetchMetrics();
                } else {
                    alert("Error al enviar.");
                    btn.innerText = "Aprobar y Enviar 🚀";
                    btn.disabled = false;
                }
            });
        });
    }

    // Directorio de Contactados Modal
    const modalContacted = document.getElementById("modal-contacted-leads");
    const closeContacted = document.getElementById("close-modal-contacted");
    
    async function openContactedModal() {
        modalContacted.style.display = "flex";
        const tbody = document.getElementById("contacted-leads-tbody");
        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding: 20px; color: var(--text-muted);">Cargando directorio...</td></tr>`;
        
        try {
            const res = await fetch("/api/leads");
            const leads = await res.json();
            tbody.innerHTML = "";
            
            if (leads.length === 0) {
                tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding: 20px; color: var(--text-muted);">No hay empresas contactadas aún.</td></tr>`;
                
            }
            
            leads.forEach(lead => {
                const tr = document.createElement("tr");
                
                const statusOptions = [
                    { value: 'pending', label: 'Pendiente' },
                    { value: 'sent', label: 'Enviado' },
                    { value: 'failed', label: 'Rebotado/Error' },
                    { value: 'esperando_aprobacion', label: 'Espera Aprobación' },
                    { value: 'negociando_horario', label: 'Negociando Horario' },
                    { value: 'agendado', label: 'Reunión Agendada' },
                    { value: 'listo_para_demo', label: 'Listo para Demo' },
                    { value: 'rechazado', label: 'Rechazado' },
                    { value: 'do_not_contact', label: 'No Contactar' },
                    { value: 'replied', label: 'Respondido' }
                ];
                
                let selectHtml = `<select class="btn badge-status bg-${lead.status}" style="background: rgba(18,16,28,0.8); border: 1px solid var(--border); color:#fff; padding: 4px 8px; font-size: 0.75rem; cursor:pointer;" onchange="changeLeadStatus(${lead.id}, this.value, this)">`;
                statusOptions.forEach(opt => {
                    selectHtml += `<option value="${opt.value}" ${lead.status === opt.value ? 'selected' : ''}>${opt.label}</option>`;
                });
                selectHtml += `</select>`;
                
                const dateStr = new Date(lead.created_at).toLocaleDateString('es-ES', {
                    day: '2-digit', month: '2-digit', year: 'numeric'
                });
                
                tr.innerHTML = `
                    <td style="font-weight: 600;">${lead.company}</td>
                    <td>${lead.email}</td>
                    <td>${selectHtml}</td>
                    <td>${dateStr}</td>
                `;
                tbody.appendChild(tr);
            });
        } catch(e) {
            console.error(e);
            tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding: 20px; color: var(--danger);">Error al cargar directorio de empresas.</td></tr>`;
        }
    }
    
    document.getElementById("card-sent-today").addEventListener("click", openContactedModal);
    document.getElementById("card-total-contacted").addEventListener("click", openContactedModal);
    document.getElementById("card-interested-leads").addEventListener("click", () => {
        const tabLink = document.querySelector('nav a[data-target="meetings"]');
        if (tabLink) tabLink.click();
    });
    closeContacted.addEventListener("click", () => {
        modalContacted.style.display = "none";
    });

    // Inbox Sync Action
    const btnSyncInbox = document.getElementById("btn-sync-inbox");
    if(btnSyncInbox) {
        btnSyncInbox.addEventListener("click", async () => {
            btnSyncInbox.innerText = "⏳ SINCRONIZANDO...";
            btnSyncInbox.disabled = true;
            try {
                await fetch("/api/inbox/sync", { method: "POST" });
                setTimeout(async () => {
                    await fetchReplies();
                    await fetchMetrics();
                    btnSyncInbox.innerText = "🔄 SINCRONIZAR GMAIL";
                    btnSyncInbox.disabled = false;
                }, 3000);
            } catch(e) {
                console.error(e);
                btnSyncInbox.innerText = "🔄 SINCRONIZAR GMAIL";
                btnSyncInbox.disabled = false;
            }
        });
    }

    // CONFIGURACIÓN (Ajustes de Cerebro)
    const btnSaveSettings = document.getElementById("btn-save-settings");
    
    // Función para renderizar previsualización en vivo resolviendo spintax y variables mockeados
    function updateEmailPreview() {
        const subjectInput = document.getElementById("settings-template-subject");
        const bodyInput = document.getElementById("settings-template-body");
        const previewSubject = document.getElementById("preview-subject");
        const previewBody = document.getElementById("preview-body");
        
        if (!subjectInput || !bodyInput || !previewSubject || !previewBody) return;
        
        let subject = subjectInput.value || "";
        let body = bodyInput.value || "";
        
        // Helper para resolver spintax {A|B|C} -> A (primera opción para consistencia)
        function resolvePreviewSpintax(text) {
            return text.replace(/\{([^{}]+)\}/g, (match, optionsStr) => {
                // Si la variable es {Nombre} o {Empresa}, no es spintax, la omitimos del split
                if (optionsStr === "Nombre" || optionsStr === "Empresa") {
                    return match;
                }
                const options = optionsStr.split('|');
                return options[0];
            });
        }
        
        const mockName = "Dr. Juan Pérez";
        const mockCompany = "Clínica Dental Sonrisas";
        
        // Reemplazar variables
        subject = subject.replace(/{Empresa}/g, mockCompany);
        body = body.replace(/{Nombre}/g, mockName).replace(/{Empresa}/g, mockCompany);
        
        // Resolver spintax
        subject = resolvePreviewSpintax(subject);
        body = resolvePreviewSpintax(body);
        
        previewSubject.innerText = subject;
        previewBody.innerHTML = body;
    }

    // Botones de inserción rápida de tags
    const insertButtons = document.querySelectorAll(".btn-insert-tag");
    insertButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetId = btn.getAttribute("data-target");
            const val = btn.getAttribute("data-val");
            const el = document.getElementById(targetId);
            if (el) {
                const start = el.selectionStart;
                const end = el.selectionEnd;
                const text = el.value;
                el.value = text.substring(0, start) + val + text.substring(end);
                el.focus();
                el.selectionStart = el.selectionEnd = start + val.length;
                updateEmailPreview();
            }
        });
    });

    // Escuchas para actualizar la previsualización al escribir
    const settingsSubjectInput = document.getElementById("settings-template-subject");
    const settingsBodyInput = document.getElementById("settings-template-body");
    if (settingsSubjectInput) {
        settingsSubjectInput.addEventListener("input", updateEmailPreview);
    }
    let quill;
    if (document.getElementById('quill-editor')) {
        quill = new Quill('#quill-editor', {
            theme: 'snow',
            modules: {
                toolbar: [
                    [{ 'header': [1, 2, false] }],
                    ['bold', 'italic', 'underline'],
                    ['link', 'blockquote', 'code-block'],
                    [{ 'list': 'ordered'}, { 'list': 'bullet' }],
                    ['clean']
                ]
            }
        });
        quill.on('text-change', function() {
            updateEmailPreview();
        });
    }

    if (settingsBodyInput) {
        settingsBodyInput.addEventListener("input", updateEmailPreview);
    }

    async function fetchSettings() {
        const res = await fetch("/api/settings");
        const data = await res.json();
        document.getElementById("settings-queue").value = data.search_queue;
        document.getElementById("settings-availability").value = data.availability;
        document.getElementById("settings-meeting-link").value = data.meeting_link || "";
        document.getElementById("settings-daily-limit").value = data.daily_limit || "80";
        document.getElementById("settings-schedule-24-7").checked = data.schedule_24_7 === "true";
        document.getElementById("settings-schedule-start").value = data.schedule_start || "09:00";
        document.getElementById("settings-schedule-end").value = data.schedule_end || "18:00";
        
        if (document.getElementById("settings-gemini-key")) {
            document.getElementById("settings-gemini-key").value = data.gemini_api_key || "";
            document.getElementById("settings-gemini-key-sync").value = data.gemini_api_key_sync || "";
            document.getElementById("settings-smtp-email").value = data.smtp_email || "";
            document.getElementById("settings-smtp-password").value = data.smtp_password || "";
            if (document.getElementById("settings-delay-min")) {
                document.getElementById("settings-delay-min").value = data.delay_min || "120";
                document.getElementById("settings-delay-max").value = data.delay_max || "300";
            }
        }

        try {
            const resTemplate = await fetch("/api/settings/template");
            const dataTemplate = await resTemplate.json();
            document.getElementById("settings-template-subject").value = dataTemplate.subject;
            if (quill) {
                quill.root.innerHTML = dataTemplate.body;
            } else {
                document.getElementById("settings-template-body").value = dataTemplate.body;
            }
            updateEmailPreview(); // Actualizar preview inicial
        } catch(e) {
            console.error("Error al cargar plantilla de correo:", e);
        }
    }

    if (btnSaveSettings) {
        btnSaveSettings.addEventListener("click", async () => {
            btnSaveSettings.innerText = "GUARDANDO...";
            btnSaveSettings.disabled = true;
            const search_queue = document.getElementById("settings-queue").value;
            const availability = document.getElementById("settings-availability").value;
            const meeting_link = document.getElementById("settings-meeting-link").value;
            const delay_min = document.getElementById("settings-delay-min") ? document.getElementById("settings-delay-min").value : "120";
            const delay_max = document.getElementById("settings-delay-max") ? document.getElementById("settings-delay-max").value : "300";
            const daily_limit = document.getElementById("settings-daily-limit").value;
            const schedule_24_7 = document.getElementById("settings-schedule-24-7").checked ? "true" : "false";
            const schedule_start = document.getElementById("settings-schedule-start").value;
            const schedule_end = document.getElementById("settings-schedule-end").value;
            
            let gemini_api_key = "";
            let gemini_api_key_sync = "";
            let smtp_email = "";
            let smtp_password = "";
            
            if (document.getElementById("settings-gemini-key")) {
                gemini_api_key = document.getElementById("settings-gemini-key").value;
                gemini_api_key_sync = document.getElementById("settings-gemini-key-sync").value;
                smtp_email = document.getElementById("settings-smtp-email").value;
                smtp_password = document.getElementById("settings-smtp-password").value;
            }
            
            const template_subject = document.getElementById("settings-template-subject").value;
            const template_body = quill ? quill.root.innerHTML : document.getElementById("settings-template-body").value;
            
            try {
                await fetch("/api/settings", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({search_queue, availability, meeting_link, gemini_api_key, gemini_api_key_sync, smtp_email, smtp_password, delay_min, delay_max, daily_limit, schedule_24_7, schedule_start, schedule_end})
                });

                await fetch("/api/settings/template", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({subject: template_subject, body: template_body})
                });
                
                alert("¡Configuración y plantilla guardadas correctamente!");
                updateEmailPreview();
            } catch(e) {
                console.error("Error al guardar ajustes:", e);
                alert("Error al guardar la configuración.");
            } finally {
                btnSaveSettings.innerText = "GUARDAR CONFIGURACIÓN";
                btnSaveSettings.disabled = false;
            }
        });
    }

    // BITÁCORA Y APRENDIZAJES
    const learningsList = document.getElementById("learnings-list");

    async function fetchLearnings() {
        const res = await fetch("/api/learnings");
        const learnings = await res.json();
        learningsList.innerHTML = "";
        
        if (learnings.length === 0) {
            learningsList.innerHTML = `<div class="glass-panel p-4 text-sm">Aún no hay aprendizajes registrados en la bitácora.</div>`;
            return;
        }

        learnings.forEach(item => {
            const card = document.createElement("div");
            card.className = "learning-card glass-panel";
            const dateStr = new Date(item.created_at).toLocaleDateString('es-ES', {
                year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
            });
            card.innerHTML = `
                <div class="date">📅 Registrado el ${dateStr}</div>
                <p>${item.content}</p>
            `;
            learningsList.appendChild(card);
        });
    }

    // btnSaveLearning ha sido eliminado ya que la bitácora es 100% autónoma.

    // REUNIONES & DEMOS
    const meetingsTbody = document.getElementById("meetings-tbody");
    const briefDisplaySection = document.getElementById("brief-display-section");
    const briefContentBox = document.getElementById("brief-content-box");
    const briefCompanyTitle = document.getElementById("brief-company-title");    async function fetchMeetings() {
        const res = await fetch("/api/leads");
        const leads = await res.json();
        meetingsTbody.innerHTML = "";
        
        // Filtrar leads que estén en estados de interés
        const interestedLeads = leads.filter(lead => 
            ['esperando_aprobacion', 'negociando_horario', 'agendado', 'listo_para_demo'].includes(lead.status)
        );

        if (interestedLeads.length === 0) {
            meetingsTbody.innerHTML = `<tr><td colspan="4" style="text-align:center;" class="text-sm">No hay leads de interés o calificados por el momento.</td></tr>`;
            // Asegurar luces de agentes en espera
            document.getElementById("agent-prep").classList.add("inactive");
            document.getElementById("agent-dev").classList.add("inactive");
            return;
        }

        let hasScheduled = false;
        let hasDemoReady = false;

        interestedLeads.forEach(lead => {
            if (lead.status === 'agendado') hasScheduled = true;
            if (lead.status === 'listo_para_demo') hasDemoReady = true;

            const tr = document.createElement("tr");
            
            // Selector de estado
            let selectHtml = `
                <select class="btn badge-status bg-${lead.status}" style="background: rgba(18,16,28,0.8); border: 1px solid var(--border); color:#fff; cursor:pointer;" onchange="changeLeadStatus(${lead.id}, this.value, this)">
                    <option value="esperando_aprobacion" ${lead.status === 'esperando_aprobacion' ? 'selected' : ''}>Espera Aprobación</option>
                    <option value="negociando_horario" ${lead.status === 'negociando_horario' ? 'selected' : ''}>Negociando Horario</option>
                    <option value="agendado" ${lead.status === 'agendado' ? 'selected' : ''}>Agendado</option>
                    <option value="listo_para_demo" ${lead.status === 'listo_para_demo' ? 'selected' : ''}>Listo para Demo</option>
                </select>
            `;
            
            // Acciones dinámicas
            let actionsHtml = "";
            if (lead.status === 'esperando_aprobacion') {
                actionsHtml = `
                    <div class="flex-actions">
                        <button class="btn btn-secondary btn-sm" style="background: var(--success); color: var(--bg-dark); border-color: var(--success); font-weight: 700;" onclick="quickApproveLead(${lead.id}, this)">
                            Aprobar y Enviar
                        </button>
                        <button class="btn-delete-subtle" onclick="deleteLead(${lead.id})" title="Eliminar prospecto">✕</button>
                    </div>
                `;
            } else {
                actionsHtml = `
                    <div class="flex-actions">
                        <button class="btn btn-secondary btn-sm" onclick="loadBrief(${lead.id})">Brief</button>
                        <a href="/api/meetings/${lead.id}/download-pptx" class="btn btn-primary btn-sm">PPTX</a>
                        <button class="btn-delete-subtle" onclick="deleteLead(${lead.id})" title="Eliminar prospecto">✕</button>
                    </div>
                `;
            }

            tr.innerHTML = `
                <td><strong>${lead.company}</strong></td>
                <td>${lead.email}</td>
                <td>${selectHtml}</td>
                <td>${actionsHtml}</td>
            `;
            meetingsTbody.appendChild(tr);
        });

        // Control dinámico de luces de los agentes en el Dashboard
        const agentScout = document.getElementById("agent-scout");
        const agentCloser = document.getElementById("agent-closer");
        const agentPrep = document.getElementById("agent-prep");
        const agentCeo = document.getElementById("agent-ceo");
        
        // Scout status is updated in fetchMetrics
        
        if (hasScheduled) {
            agentPrep.classList.remove("inactive");
            agentPrep.querySelector(".status-dot").innerText = "Preparando PPTX";
        } else {
            agentPrep.classList.add("inactive");
            agentPrep.querySelector(".status-dot").innerText = "Espera";
        }
    };

    window.changeLeadStatus = async function(leadId, newStatus, selectEl = null) {
        if (selectEl) {
            selectEl.className = `btn badge-status bg-${newStatus}`;
        }
        await fetch(`/api/leads/${leadId}/status`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({status: newStatus})
        });
        fetchMeetings();
        fetchMetrics();
    };

    window.quickApproveLead = async function(leadId, btnEl) {
        const originalText = btnEl.innerText;
        btnEl.innerText = "⏳ Enviando...";
        btnEl.disabled = true;
        try {
            const res = await fetch(`/api/leads/${leadId}/approve-proposed-reply`, { method: "POST" });
            if (res.ok) {
                alert("✅ Correo aprobado y enviado con éxito.");
                fetchMeetings();
                fetchMetrics();
            } else {
                const data = await res.json();
                alert("❌ Error: " + (data.detail || "No se pudo aprobar la respuesta."));
            }
        } catch (e) {
            console.error(e);
            alert("❌ Error de red al intentar aprobar la respuesta.");
        } finally {
            btnEl.innerText = originalText;
            btnEl.disabled = false;
        }
    };

    window.controlBot = async function(action) {
        try {
            const res = await fetch(`/api/bot/${action}`, { method: "POST" });
            const data = await res.json();
            if (data.success) {
                console.log(`Bot ${action} success`);
            } else {
                console.log(`Bot ${action} returned false`);
            }
        } catch(e) {
            console.error(e);
        }
    };

    window.loadBrief = async function(leadId) {
        briefDisplaySection.style.display = "block";
        briefContentBox.innerHTML = `
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px 0; text-align: center; width: 100%;">
                <div style="margin-bottom: 20px; width: 80%; max-width: 400px;">
                    <div style="color: var(--secondary); font-weight: 700; font-size: 1.1rem; margin-bottom: 12px; font-family: 'Outfit', sans-serif;">Analizando prospecto con Egasis AI Brain...</div>
                    <div class="famous-loading-bar-container">
                        <div class="famous-loading-bar-fill"></div>
                    </div>
                </div>
                <div style="color: var(--text-muted); font-size: 0.85rem; max-width: 450px; line-height: 1.6; font-family: 'Inter', sans-serif;">
                    Gemini está analizando la web de la empresa, identificando debilidades comerciales y estructurando un Call Brief altamente estratégico para tu llamada de ventas...
                </div>
            </div>
        `;
        briefContentBox.scrollTop = 0;
        
        try {
            const res = await fetch(`/api/meetings/${leadId}/brief`);
            const data = await res.json();
            briefCompanyTitle.innerText = data.company;
            briefContentBox.innerHTML = data.brief;
        } catch (e) {
            briefContentBox.innerHTML = "<p style='color:var(--danger)'>Error al generar el Call Brief. Inténtalo de nuevo.</p>";
        }
    };

    // Funciones de Modales de Agentes
    window.openAgentModal = async function(agentType) {
        const modal = document.getElementById("agent-modal");
        const title = document.getElementById("modal-title");
        const content = document.getElementById("modal-content");
        modal.style.display = "flex";
        content.innerHTML = "Cargando datos del agente...";

        if (agentType === 'scout') {
            title.innerText = "🕵️‍♂️ Agente Scout - Cola de Búsqueda";
            try {
                const res = await fetch("/api/settings");
                const data = await res.json();
                const queue = data.search_queue.split('\n').filter(q => q.trim() !== '');
                const currentIdx = data.current_queue_index || 0;
                
                let html = "<p>Esta es la lista de ciudades que el Scout recorrerá cada día a las 8:00 AM:</p><ul style='margin-left:20px; margin-top:10px;'>";
                queue.forEach((q, i) => {
                    if (i === currentIdx) {
                        html += `<li><strong style="color:var(--primary)">👉 ${q} (En progreso)</strong></li>`;
                    } else if (i < currentIdx) {
                        html += `<li><del style="color:var(--text-muted)">${q} (Completado)</del></li>`;
                    } else {
                        html += `<li>${q}</li>`;
                    }
                });
                html += "</ul>";
                content.innerHTML = html;
            } catch (e) {
                content.innerHTML = "Error cargando la cola de búsqueda.";
            }
        } else if (agentType === 'closer') {
            title.innerText = "💬 Agente Closer - Negociaciones";
            try {
                const res = await fetch("/api/leads");
                const leads = await res.json();
                const negociando = leads.filter(l => ['replied', 'negociando_horario'].includes(l.status));
                if (negociando.length === 0) {
                    content.innerHTML = "<p>Actualmente no hay leads en fase de negociación de horarios.</p>";
                } else {
                    let html = "<p>Leads actualmente en negociación y seguimiento automático:</p><ul style='margin-left:20px; margin-top:10px;'>";
                    negociando.forEach(l => {
                        html += `<li><strong>${l.company}</strong> (${l.email}) - Estado: <span style="color:var(--secondary)">${l.status}</span></li>`;
                    });
                    html += "</ul>";
                    content.innerHTML = html;
                }
            } catch (e) {
                content.innerHTML = "Error cargando negociaciones.";
            }
        } else if (agentType === 'ceo') {
            title.innerText = "👑 CEO Supervisor - Visión Global";
            content.innerHTML = `
                <p>Estás en la vista de supervisión global.</p>
                <div style="margin-top:16px; padding:16px; background:rgba(0,0,0,0.3); border-radius:8px;">
                    <p><strong>Salud del Sistema:</strong> <span style="color:var(--success)">ÓPTIMA</span></p>
                    <p><strong>Cronjob 8 AM:</strong> <span style="color:var(--success)">PROGRAMADO</span></p>
                    <p><strong>Bucle de Auto-Aprendizaje:</strong> <span style="color:var(--success)">ACTIVO</span></p>
                    <p style="margin-top:10px; font-size:0.85rem; color:var(--text-muted)">El sistema está corriendo de forma autónoma. Puedes revisar la bitácora para ver qué está aprendiendo la IA de las respuestas recibidas.</p>
                </div>
            `;
        } else if (agentType === 'analyst') {
            title.innerText = "📈 Agente Analista - Procesamiento NLP";
            content.innerHTML = `
                <p><strong>Estado:</strong> Corriendo en Segundo Plano</p>
                <p>Este agente evalúa el tono y el análisis de sentimiento de los correos entrantes utilizando Modelos de Lenguaje Natural (NLP). Ayuda al Closer a decidir la agresividad del seguimiento.</p>
            `;
        } else if (agentType === 'scorer') {
            title.innerText = "🎯 Agente Calificador - Lead Scoring";
            content.innerHTML = `
                <p><strong>Estado:</strong> Corriendo en Segundo Plano</p>
                <p>Cruza datos de los dominios extraídos y estima el volumen de facturación o "tier" de cada lead. Asigna prioridades altas a empresas consolidadas.</p>
            `;
        } else {
            title.innerText = "Agente en Espera";
            content.innerHTML = "<p>Este agente se activará automáticamente cuando un lead pase a las siguientes fases del embudo.</p>";
        }
    };

    window.closeAgentModal = function() {
        document.getElementById("agent-modal").style.display = "none";
    };

    window.deleteLead = async function(leadId) {
        if (!confirm("¿Estás seguro de que deseas eliminar este prospecto y todas sus interacciones (mensajes y respuestas)?")) {
            return;
        }
        try {
            const res = await fetch(`/api/leads/${leadId}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.success) {
                fetchReplies();
                fetchMeetings();
                fetchMetrics();
            } else {
                alert("❌ Error: " + (data.detail || "No se pudo eliminar el lead."));
            }
        } catch (e) {
            console.error(e);
            alert("❌ Error de red al intentar eliminar el lead.");
        }
    };

    // Carga inicial
    fetchMetrics();
    setInterval(fetchMetrics, 5000);
});
