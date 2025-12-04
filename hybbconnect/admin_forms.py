from django import forms

class SalarySlipUploadForm(forms.Form):
    file = forms.FileField(
        label="Select Excel or CSV File",
        help_text="Upload .xlsx or .csv file containing salary slip data"
    )
