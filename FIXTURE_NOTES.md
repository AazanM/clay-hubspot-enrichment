# Fixture Notes

This document maps test scenarios and edge cases to specific Row IDs in `fixtures/clay_export.csv`.

| Edge Case | Row ID(s) | Lead / Company Details | Expected Pipeline Behavior |
| :--- | :--- | :--- | :--- |
| **Missing Email** | 5, 12, 20, 27, 35 | David Brooks (`quantex.example.com`), Julian Kemp (`kempmedia.example.com`), Noah Patel (`omniflow.example.com`), Maya Lin (`archondesign.example.com`), Isabella Rossi (`veronasystems.example.com`) | Enrichment providers resolve the email address via domain or name lookups during waterfall execution. |
| **Free Mail Address** | 7 | Alex Morgan (`alex.morgan@gmail.com`) | Flagged as `free_mail`. ICP scoring denies points for business email rule. |
| **Role Address** | 8 | Support Desk (`info@novasolutions.example.com`) | Flagged as `role_address`. ICP tier is capped at tier `C`. |
| **Invalid Email** | 9 | Lucas Gray (`marcus.invalid@@techpulse.example.com`) | Flagged as `invalid_email`. Dropped/rejected before HubSpot sync; never pushed. |
| **In-Batch Duplicate** | 10, 11 | Elena Rostova (`elena.rostova@cloudscale.example.com`) | Row 10 has complete profile details and is retained; Row 11 is marked `skip_duplicate_in_batch`. |
| **HubSpot Email Match** | 1, 2, 3 | Sarah Chen (`c-1001`), Marcus Vance (`c-1002`), Olivia Taylor (`c-1003`) | Matches existing contact by email; updates contact record without creating duplicate. |
| **HubSpot Domain Match** | 14, 15 | Liam Wright (`solarislogic.example.com`), Sophia Martinez (`auroraai.example.com`) | Contact is new (`create`), but company domain matches existing HubSpot company (`co-2004`, `co-2005`), associating contact with existing company. |
| **HubSpot Company Name Match** | 16 | Daniel Kim (`Vanguard Analytics`) | Company domain differs (`vanguardanalytics.example.com` vs `vanguard-analytics.example.com`), but company name matches fuzzy threshold (>= 0.88), linking to `co-2006`. |
