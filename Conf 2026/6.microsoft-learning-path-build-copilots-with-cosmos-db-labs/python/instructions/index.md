---
title: Python SDK labs
nav_order: 3
has_children: true
has_toc: false
layout: default
---

# Python SDK labs

Below is a list of the labs for the Azure Cosmos DB Python SDK modules.

## Common setup instructions

{% assign labs = site.pages | where_exp:"page", "page.url contains 'common/instructions'" %}
| Module | Lab |
| --- | --- |
{% for activity in labs  %}| {{ activity.lab.module }} | [{{ activity.lab.title }}]({{ site.baseurl }}{{ activity.url }}) |
{% endfor %}

## Lab instructions

{% assign labs = site.pages | where_exp:"page", "page.url contains 'python/instructions'" %}
| Module | Lab |
| --- | --- |
{% for activity in labs  %}| {{ activity.lab.module }} | [{{ activity.lab.title }}]({{ site.baseurl }}{{ activity.url }}) |
{% endfor %}
