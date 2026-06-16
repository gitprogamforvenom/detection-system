from django import forms 

class MessageForm(forms.Form):
    text = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control', 
            'placeholder': 'Enter your email content here...',
            'rows': 8
        }),
        required=False,
        label='Email Text'
    )
    email_file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.txt,.eml,.msg,.csv'
        }),
        required=False,
        label='Upload Email File or CSV Dataset'
    )
    
class FeedbackForm(forms.Form):
    """Form for user feedback on predictions"""
    email_text = forms.CharField(widget=forms.HiddenInput())
    predicted_class = forms.CharField(widget=forms.HiddenInput())
    actual_class = forms.ChoiceField(
        choices=[('spam', 'Spam'), ('ham', 'Not Spam')],
        widget=forms.RadioSelect,
        label='Correct Classification'
    )
    feedback = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        required=False,
        label='Additional Comments'
    )