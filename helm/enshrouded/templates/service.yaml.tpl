apiVersion: v1
kind: Service
metadata:
  name: {{ include "enshrouded.fullname" . }}
  namespace: {{ .Values.namespace }}
  labels:
{{ include "enshrouded.labels" . | indent 4 }}
spec:
  type: {{ .Values.service.type }}
  selector:
    app.kubernetes.io/name: {{ include "enshrouded.name" . }}
    app.kubernetes.io/instance: {{ .Release.Name }}
  ports:
    - name: game-udp
      protocol: UDP
      port: {{ .Values.service.gamePort }}
      targetPort: game-udp
      {{- if eq .Values.service.type "NodePort" }}
      nodePort: {{ .Values.service.gameNodePort }}
      {{- end }}
    - name: steam-query
      protocol: UDP
      port: {{ .Values.service.queryPort }}
      targetPort: query-udp
      {{- if eq .Values.service.type "NodePort" }}
      nodePort: {{ .Values.service.queryNodePort }}
      {{- end }}
    {{- if and .Values.statsApi.enabled .Values.service.statsApi.enabled }}
    - name: stats-api
      protocol: TCP
      port: {{ .Values.service.statsApi.port }}
      targetPort: stats-api
      {{- if eq .Values.service.type "NodePort" }}
      nodePort: {{ .Values.service.statsApi.nodePort }}
      {{- end }}
    {{- end }}
    {{- if .Values.service.saveImport.enabled }}
    - name: import-ui
      protocol: TCP
      port: {{ .Values.service.saveImport.port }}
      targetPort: import-ui
      {{- if eq .Values.service.type "NodePort" }}
      nodePort: {{ .Values.service.saveImport.nodePort }}
      {{- end }}
    {{- end }}
