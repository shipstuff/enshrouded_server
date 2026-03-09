{{- if not .Values.persistence.existingClaim }}
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {{ include "enshrouded.pvcName" . }}
  namespace: {{ .Values.namespace }}
  labels:
{{ include "enshrouded.labels" . | indent 4 }}
spec:
  {{- if .Values.persistence.storageClassName }}
  storageClassName: {{ .Values.persistence.storageClassName | quote }}
  {{- end }}
  accessModes:
    - {{ .Values.persistence.accessMode }}
  resources:
    requests:
      storage: {{ .Values.persistence.size }}
{{- end }}
