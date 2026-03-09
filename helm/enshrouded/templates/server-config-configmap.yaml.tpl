{{- if and (eq .Values.serverConfig.mode "managed") .Values.serverConfig.inlineJson }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "enshrouded.managedConfigTemplateName" . }}
  namespace: {{ .Values.namespace }}
  labels:
{{ include "enshrouded.labels" . | indent 4 }}
data:
  enshrouded_server.json: |
{{ .Values.serverConfig.inlineJson | toPrettyJson | indent 4 }}
{{- end }}
