{
    'categorisation': {
        'codeable': False, 
        'codings': [
            {
                'code': '47110',
                'code_description': 'Retail sale in non-specialised stores with food, beverages or tobacco predominating', 'confidence': 0.9
            },
            {
                'code': '47290',
                'code_description': 'Other retail sale of food in specialised stores',
                'confidence': 0.8
            }, 
            {
                'code': '47810',
                'code_description': 'Retail sale via stalls and markets of food, beverages and tobacco products',
                'confidence': 0.6
            }, 
            {
                'code': '47210',
                'code_description': 'Retail sale of fruit and vegetables in specialised stores',
                'confidence': 0.5
            }
        ], 
        'justification': "The company's main activity is selling food and goods to the general public, which aligns with the SIC code 47110 for 'Retail sale in non-specialised stores with food, beverages or tobacco predominating'. The job title 'Checkout operator' and job description 'I scan shopping, take cash and handle customer queries' further support this classification. However, there are other possible SIC codes that could be considered, such as 47290 'Other retail sale of food in specialised stores' or 47810 'Retail sale via stalls and markets of food, beverages and tobacco products'. To determine the most accurate SIC code, it is important to know if the supermarket is part of a larger chain or an independent store.",
        'sic_code': '47110',
        'sic_description': 'Retail sale in non-specialised stores with food, beverages or tobacco predominating'
    },
    'follow_up': {
        'questions': [
            {
                'follow_up_id': 'f1.1',
                'question_name': 'ai_assist_followup',
                'question_text': 'Is the supermarket part of a larger chain or is it an independent store?',
                'response_type': 'text',
                'select_options': []
            }, 
            {
                'follow_up_id': 'f1.2',
                'question_name': 'ai_assist_followup',
                'question_text': "Which of these best describes your organisation's activities?",
                'response_type': 'select',
                'select_options': [
                    'Retail sale in non-specialised stores with food, beverages or tobacco predominating',
                    'Other retail sale of food in specialised stores',
                    'Retail sale via stalls and markets of food, beverages and tobacco products',
                    'Retail sale of fruit and vegetables in specialised stores',
                    'None of the above']
            }
        ]
    }
}