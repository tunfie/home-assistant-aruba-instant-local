# Public release checklist

This directory is the clean source package. Do not publish the parent workspace.

1. Sign in from the owner's private environment. Intended repository:
   tunfie/home-assistant-aruba-instant-local (public). No GitHub connection is
   permitted from the current work environment.
2. Confirmed by owner: MIT license, maintainer tunfie. LICENSE is included.
3. Manifest already targets the intended repository URL, /issues and @tunfie.
   Verify these match the repository actually created.
4. Approved MIT LICENSE text is present.
5. Run tests, hassfest and HACS validation on GitHub; fix all failures.
6. Review the source for secrets. Test an isolated install/config flow in a clean
   Home Assistant installation. Test unload, API errors, offline controller,
   changed credentials and another firmware model before declaring broad support.
7. Publish a prerelease tagged 0.1.0-beta.1 and attach the clean install ZIP.
8. Add it as a custom repository for beta users. Collect compatibility reports.
9. Once stable and checks pass, submit the repository to the Marketplace/HACS
   catalog under the owner's account. Acceptance is decided by catalog maintainers.

Current scope is monitoring only. Firmware control and guest disconnect must be
implemented and tested separately with explicit safeguards before claiming support.
