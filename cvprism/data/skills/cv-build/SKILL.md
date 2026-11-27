---
name: cv-build
description: Build a tailored CV with cvprism for a role or a job description. Use when the user says /cv-build, "build my CV for <role>", or pastes a job posting and asks for a matching CV.
---

# cv-build (cvprism)

1. Run `cvprism status` to check that this device is the **hub**. If it is a spoke, explain that CVs are built on the hub device.
2. For a role: `cvprism build --role <role>` (roles live in the vault's `roles/` folder).
   For a job description: save it to a file and run `cvprism build --jd <file>`.
3. Report the output paths, the page count, any rejected bullets (claims without evidence) and the gap report.
4. Never add claims, numbers or skills that are not in the build output; the honesty gate already rejected them.
