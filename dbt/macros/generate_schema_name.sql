{#
  Without this override dbt CONCATENATES the profile schema with the model's
  +schema, producing marts_staging / marts_intermediate — i.e. two brand-new
  schemas on a shared database. This estate's rule is to build into the
  existing staging / intermediate / marts schemas using a unique model-name
  prefix instead, so the custom schema name is used verbatim.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
