Update your Syxplain account
=============================

Your Syxplain account requires the following action<#if requiredActions?size gt 1>s</#if>:

<#list requiredActions as reqActionItem>
- ${msg("requiredAction.${reqActionItem}")}
</#list>

Click the link below to proceed:
${link}

This link will expire in ${linkExpiration}.

If you didn't request this, you can safely ignore this email.

--
Syxplain - Neurosymbolic Scientific Discovery
