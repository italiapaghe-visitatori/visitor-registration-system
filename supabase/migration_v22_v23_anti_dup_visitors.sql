-- MIGRATION v22+v23 — Anti-duplicato firme + RLS anon SELECT visitors
-- ========================================================================
-- Applicate live su Supabase il 14/05/2026 durante l'evento MD.
-- Committate in repo per disaster recovery / staging clone / audit storico.
--
-- v22: trigger BEFORE INSERT su visitors che intercetta nuovi insert
-- con guest_id che ha già uno stub unsigned (signature NULL, badge_number
-- valorizzato) e fa UPDATE invece. Previene duplicati firma quando il
-- frontend submit-ta una nuova riga invece di patchare lo stub esistente.
--
-- v23: policy anon SELECT su visitors. Necessaria perché il frontend QR
-- (anon) deve leggere visitors per costruire signedIds (filtro lista) e
-- preAssignedVisitorByGuest (sapere quale stub patchare). Senza questa
-- policy, il filtro signedIds è sempre vuoto → frontend mostra tutti gli
-- ospiti come da firmare.

-- ============================================================
-- v22 — Trigger anti-duplicato visitor
-- ============================================================
CREATE OR REPLACE FUNCTION public.tg_prevent_visitor_dup()
RETURNS TRIGGER AS $$
DECLARE
  existing_stub_id UUID;
BEGIN
  -- Si attiva solo per firma da QR/kiosk (guest_id valorizzato + signature)
  IF NEW.guest_id IS NULL OR NEW.signature IS NULL THEN
    RETURN NEW;
  END IF;

  -- Cerca stub pre-assegnato per quel guest_id (unsigned, ha badge)
  SELECT id INTO existing_stub_id
    FROM public.visitors
   WHERE guest_id = NEW.guest_id
     AND signature IS NULL
     AND badge_number IS NOT NULL
   LIMIT 1;

  -- Nessuno stub → INSERT normale (walk-in al kiosk)
  IF existing_stub_id IS NULL THEN
    RETURN NEW;
  END IF;

  -- Stub trovato → UPDATE con dati firma invece di nuovo record
  UPDATE public.visitors
     SET signature             = NEW.signature,
         document_id           = COALESCE(NEW.document_id,           document_id),
         document_type         = COALESCE(NEW.document_type,         document_type),
         email                 = COALESCE(NEW.email,                 email),
         phone                 = COALESCE(NEW.phone,                 phone),
         data_consent          = COALESCE(NEW.data_consent,          data_consent),
         badge_agreement       = COALESCE(NEW.badge_agreement,       badge_agreement),
         access_rules_consent  = COALESCE(NEW.access_rules_consent,  access_rules_consent),
         access_rules_at       = COALESCE(NEW.access_rules_at,       access_rules_at),
         access_rules_version  = COALESCE(NEW.access_rules_version,  access_rules_version),
         access_rules_opened   = COALESCE(NEW.access_rules_opened,   access_rules_opened),
         consent_ip            = COALESCE(NEW.consent_ip,            consent_ip),
         consent_user_agent    = COALESCE(NEW.consent_user_agent,    consent_user_agent),
         access_rules_pdf_hash = COALESCE(NEW.access_rules_pdf_hash, access_rules_pdf_hash),
         access_rules_pdf_size = COALESCE(NEW.access_rules_pdf_size, access_rules_pdf_size)
   WHERE id = existing_stub_id;

  RETURN NULL; -- salta l'INSERT, lo stub è stato aggiornato
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS visitors_prevent_dup_bi ON public.visitors;
CREATE TRIGGER visitors_prevent_dup_bi
BEFORE INSERT ON public.visitors
FOR EACH ROW EXECUTE FUNCTION public.tg_prevent_visitor_dup();

-- ============================================================
-- v23 — Policy anon SELECT su visitors (per frontend QR)
-- ============================================================
DROP POLICY IF EXISTS "anon_select_visitors" ON public.visitors;
CREATE POLICY "anon_select_visitors"
  ON public.visitors
  FOR SELECT
  USING (true);
