---
title: 'Common setup instructions'
has_children: true
has_toc: false
layout: default
nav_order: 2
---

# Common setup instructions

The following setup instructions apply to all labs in this repository.

{% assign labs = site.pages | where_exp:"page", "page.url contains 'common/instructions'" %}
| Module | Lab |
| --- | --- |
{% for activity in labs  %}| {{ activity.lab.module }} | [{{ activity.lab.title }}]({{ site.baseurl }}{{ activity.url }}) |
{% endfor %}